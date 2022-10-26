import base64
import io
import json
import os
import requests
from argon2 import low_level
from base64 import urlsafe_b64encode
from hashlib import blake2b
from http.cookies import SimpleCookie
from PIL import Image
from PIL.PngImagePlugin import PngInfo
from wordcloud import WordCloud


class Nais():
    def __init__(self):
        super().__init__()
        self._session = requests.session()
        self._headers = {}
        self._cookies = SimpleCookie()
        self._accessKey = None
        self.settings = {
            'root': 'https://api.novelai.net',
            'timeout': 30.0,
            'output_folder': '.data',
        }

        if not os.path.exists(self.output_folder()):
            os.makedirs(self.output_folder(), exist_ok=True)

    def output_folder(self):
        return self.settings['output_folder']

    def login(self, email: str, password: str):
        pre_salt = password[:6] + email + "novelai_data_access_key"
        blake = blake2b(digest_size=16)
        blake.update(pre_salt.encode())
        salt = blake.digest()
        raw = low_level.hash_secret_raw(password.encode(), salt, 2, int(2000000 / 1024), 1, 64, low_level.Type.ID)
        hashed = urlsafe_b64encode(raw).decode()
        resp = self.post('/user/login', {"key": hashed[:64]})
        token = json.loads(resp.content.decode('utf-8'))['accessToken']
        self._headers['Authorization'] = f"Bearer {token}"
        print('logged in.')

    def post(self, url, args):
        kwargs = {
            'timeout': self.settings['timeout'],
            'cookies': self._cookies,
            'headers': self._headers,
            'json' if type(args) is dict else 'data': args,
        }
        return self._session.post(self.settings['root'] + url, **kwargs)

    def gen_image(self, args):
        if type(args) is str:
            args = json.loads(args)
        resp = self.post('/ai/generate-image', args)
        print(resp)
        if resp.status_code != 201:
            raise RuntimeError("Bad Response!")
        text = resp.content.decode('utf-8')
        data = {}
        for l in text.splitlines():
            l = l.strip()
            if not l:
                continue
            k, v = l.split(':')
            data[k] = v
        bin = base64.b64decode(data['data'])
        return bin

    def gen_wc(self, prompt, wc_settings):
        tags = [x.strip() for x in prompt.split(',')]
        scaled = {}
        for tag in tags:
            if tag.startswith('{'):
                scale = 1.05 ** tag.count('{')
                tag = tag.replace('{', '').replace('}', '')
            elif tag.startswith('['):
                scale = 0.95238 ** tag.count('[')
                tag = tag.replace('[', '').replace(']', '')
            else:
                scale = 1
            if tag not in scaled:
                scaled[tag] = scale
            else:
                scaled[tag] = max(scaled[tag], scale)
        return WordCloud(**wc_settings).generate_from_frequencies(scaled)

    def save_image(self, name, args):
        base = os.path.join(self.output_folder(), name)
        if type(args) is str:
            try:
                args = json.loads(args)
            except Exception as e:
                print(e)
                return
        with open(f'{base}.json', 'wt') as f:
            json.dump(args, f, indent=2)
        im_bin = self.gen_image(args)
        im = Image.open(io.BytesIO(im_bin))

        metadata = PngInfo()
        metadata.add_text("Title", 'AI generated image')
        metadata.add_text("Software", 'NovelAI')
        metadata.add_text("Source", 'Stable Diffusion 81274D13')  # FIXME
        metadata.add_text("Description", args["input"])
        metadata.add_text("Comment", json.dumps(args["parameters"], sort_keys=True))

        im.save(f'{base}.png', 'PNG', pnginfo=metadata)
        im.thumbnail((64, 64), Image.ANTIALIAS)
        im.save(f'{base}_tm.png', "PNG")
        self.gen_wc(args['input'], {
                'width': 512,
                'height': 512,
                'relative_scaling': 1,
                'normalize_plurals': False,
                'background_color': "white",
                'mode': "RGB",
                'include_numbers': True,
                'regexp': r"[\w']+",
            }).to_file(f'{base}_wc_pos.png')
        self.gen_wc(args['parameters']['uc'], {
                'width': 512,
                'height': 512,
                'relative_scaling': 1,
                'normalize_plurals': False,
                'background_color': "black",
                'mode': "RGB",
                'include_numbers': True,
                'regexp': r"[\w']+",
            }).to_file(f'{base}_wc_neg.png')

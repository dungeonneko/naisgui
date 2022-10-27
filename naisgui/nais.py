import base64
import io
import json
import os
import requests
import naisgui.util
from argon2 import low_level
from base64 import urlsafe_b64encode
from hashlib import blake2b
from http.cookies import SimpleCookie
from PIL import Image
from PIL.PngImagePlugin import PngInfo
from wordcloud import WordCloud


NAIS_DATA_COMPLETE = 0
NAIS_DATA_INCOMPLETE = 1
NAIS_DATA_ERROR = -1


def nais_data_from_image(arg):
    try:
        im = Image.open(arg)
        im.load()
        print(im.info)
    except Exception as e:
        return {}, NAIS_DATA_ERROR
    try:
        # NovelAI
        return {
                   'input': im.info['Description'],
                   'model': 'nai-diffusion',
                   'parameters': json.loads(im.info['Comment'])
               }, NAIS_DATA_COMPLETE
    except Exception as e:
        pass
    try:
        data = {
            'input': '',
            'parameters': {},
        }
        # AIBooru?
        afterNegativePrompt = False
        for x in im.info['parameters'].split('\n'):
            if not afterNegativePrompt:
                if x.startswith('Negative prompt:'):
                    data['parameters']['uc'] = x[len('Negative prompt:'):]
                    afterNegativePrompt = True
                else:
                    temp = ', '.join([x.strip() for x in x.split(',') if x])
                    for z, w in [('{ ', '{'), (' }', '}'), ('[ ', '['), (' ]', ']'), ('( ', '('), (' )', ')')]:
                        temp = temp.replace(z, w)
                    temp += ', '
                    data['input'] += temp
            else:
                for y in x.split(','):
                    y = y.strip()
                    if y.startswith('Steps:'):
                        data['parameters']['steps'] = int(y[len('Steps:'):].strip())
                    elif y.startswith('CFG scale:'):
                        data['parameters']['scale'] = int(y[len('CFG scale:'):].strip())
                    elif y.startswith('Seed:'):
                        data['parameters']['seed'] = int(y[len('Seed:'):].strip())
                    elif y.startswith('Size:'):
                        y = y[len('Size:'):].strip()
                        w, h = y.split('x')
                        data['parameters']['width'] = int(w.strip())
                        data['parameters']['height'] = int(h.strip())
                    elif y.startswith('Denoising strength:'):
                        data['parameters']['strength'] = float(y[len('Denoising strength:'):].strip())
                    else:
                        print('unsupported parameter:', y)
        data['input'] = ', '.join([x.strip() for x in data['input'].split(',') if x.strip()])
        return data, NAIS_DATA_INCOMPLETE
    except Exception as e:
        print(e)
        return {}, NAIS_DATA_ERROR


def nais_data_from_local_image(path):
    return nais_data_from_image(path)


def nais_data_from_uploaded_image(path):
    response = requests.get(path)
    return nais_data_from_image(io.BytesIO(response.content))


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
            f.write(naisgui.util.json_to_text(args))
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
                'stopwords': '',
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
                'stopwords': '',
            }).to_file(f'{base}_wc_neg.png')

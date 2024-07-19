import requests
import m3u8
from Crypto.Util.Padding import pad
from Crypto.Cipher import AES
import tqdm


HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; WOW64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/86.0.4240.198 Safari/537.36"
}


def download_key(key_uri: bytes):
    response = requests.get(key_uri, headers=HEADERS)
    return response.content


def decrypt_segment(segment: m3u8.Segment, key: bytes, iv: bytes):
    response = requests.get(segment.absolute_uri, headers=HEADERS)
    encrypted_data = response.content
    cipher_text = pad(encrypted_data, AES.block_size)
    cipher = AES.new(key, AES.MODE_CBC, iv)
    decrypted_data = cipher.decrypt(cipher_text)
    return decrypted_data


def no_decrypt_segment(segment: m3u8.Segment):
    response = requests.get(segment.absolute_uri, headers=HEADERS)
    return response.content


def download_m3u8_video(url, save_name):
    # 构造 m3u8 对象
    m3u8_obj = m3u8.load(url, headers=HEADERS)
    # 获取流媒体片段地址
    segments = m3u8_obj.segments
    # 预留 key 和 iv
    key = None
    iv = None
    # 如果存在密钥，获取 key 和 iv
    if m3u8_obj.keys:
        key_uri = m3u8_obj.keys[-1].uri
        key = download_key(key_uri)
        iv = key[:16]
    with open(f'{save_name}.mp4', "wb") as f:
        for seg in tqdm.tqdm(segments, desc=save_name):
            if m3u8_obj.keys:
                decrypted_data = decrypt_segment(seg, key, iv)
                segment_data = decrypted_data
            else:
                segment_data = no_decrypt_segment(seg)
            f.write(segment_data)
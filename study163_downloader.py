from concurrent.futures import ThreadPoolExecutor
import os
import re
from Crypto.Cipher import AES
from Crypto.Util.Padding import unpad
import base64
from urllib.parse import quote

import requests

from m3u8_handler import download_m3u8_video
from read_config import get_ini_config


KEY = b'3fp4xs922ouw5q72'


def sanitize_filename(filename):
    # 定义不能使用的字符
    invalid_chars = r'<>:"/\\|?*'
    # 定义保留的文件名
    reserved_names = ["CON", "PRN", "AUX", "NUL", "COM1", "COM2", "COM3", "COM4", "COM5", "COM6", "COM7", "COM8", "COM9", "LPT1", "LPT2", "LPT3", "LPT4", "LPT5", "LPT6", "LPT7", "LPT8", "LPT9"]

    # 替换掉不能使用的字符
    filename = re.sub(r'[<>:"/\\|?*]', '', filename)

    # 检查是否是保留的文件名
    if filename.upper() in reserved_names:
        filename = "_RESERVED_" + filename

    return filename


def study_163_k_decrypt_2_token(encrypted_text, key=KEY, mode=AES.MODE_CBC, padding='pkcs7'):
    """从 k 值中解密出 token"""
    cipher = AES.new(key, mode)
    ciphertext = base64.b64decode(encrypted_text)
    decrypted_text = unpad(cipher.decrypt(ciphertext), AES.block_size, style=padding)[22:-2].decode('utf-8')
    token = f'https:{decrypted_text}'
    # print(f'token: {token}\n')
    return token


class Downloader:
    """
    cookie 中的有效参数是 STUDY_SESS
    """

    def __init__(self, cookie: str, course_id: str | int, save_dir_name: str = 'output'):
        self.cookie = cookie
        self.course_id = course_id
        self.save_dir_name = save_dir_name

    def get_lessons_list(self):
        """整理散乱的考课程信息,懒得怎么写的优雅了，直接正则和循环处理这些信息"""
        url = "https://study.163.com/dwr/call/plaincall/PlanNewBean.getPlanCourseDetail.dwr"
        payload = f"callCount=1\nscriptSessionId=$scriptSessionId190\nhttpSessionId=5ce8ef1c12f540dda8f740fa3d05152c\nc0-scriptName=PlanNewBean\nc0-methodName=getPlanCourseDetail\nc0-id=0\nc0-param0=string:{self.course_id}\nc0-param1=number:0\nc0-param2=null:null\nbatchId=1721309910373"
        headers = {
            'Content-Type': 'text/plain'
        }
        response = requests.request("POST", url, headers=headers, data=payload)
        res = {}
        s_index_list = set(re.findall('(s\\d+)\\.', response.text))
        for item in s_index_list:
            res[item] = {}

        id_list = re.findall('(s\\d+)\\.id=(\\d+);', response.text)
        for item in id_list:
            k, v = item
            res[k].update({'lesson_id': v})

        # chapter_id 是否为空可以用来过滤飞课程的 item
        chapter_id_list = re.findall('(s\\d+)\\.chapterId=(\\d+);', response.text)
        for item in chapter_id_list:
            k, v = item
            res[k].update({'chapter_id': v})

        position_list = re.findall('(s\\d+)\\.position=(\\d+);', response.text)
        for item in position_list:
            k, v = item
            res[k].update({'position': int(v) + 1})

        name_list = re.findall('(s\\d+)\\.lessonName="(.+?)";', response.text)
        name_list = [(item[0], item[1].encode('ascii').decode('unicode-escape')) for item in name_list]
        for item in name_list:
            k, v = item
            res[k].update({'name': v})

        r = []
        for k, v in res.items():
            if v.get('chapter_id'):
                r.append(v)
        r.sort(key=lambda i: i['position'])

        lesson_list = []
        for item in r:
            if item["position"] < 10:
                lesson_list.append({
                    'lesson_id': item["lesson_id"],
                    'lesson_name': sanitize_filename(f'0{item["position"]}.{item["name"]}').strip()
                })
            else:
                lesson_list.append({
                    'lesson_id': item["lesson_id"],
                    'lesson_name': sanitize_filename(f'{item["position"]}.{item["name"]}').strip()
                })
        print(f'获取课程信息：{len(lesson_list)} 个')
        # print(lesson_list)
        return lesson_list

    def get_signature(self, lesson_id: str | int, ) -> tuple | None:
        """获取 signature ，为后续获取视频信息做准备"""
        url = "https://study.163.com/dwr/call/plaincall/LessonLearnBean.getVideoLearnInfo.dwr"
        payload = f"callCount=1\nscriptSessionId=$scriptSessionId190\nhttpSessionId=c8eb06591d8d49a0bdddbe4722f28a94\nc0-scriptName=LessonLearnBean\nc0-methodName=getVideoLearnInfo\nc0-id=0\nc0-param0=string:{lesson_id}\nc0-param1=string:{self.course_id}\nbatchId=1721276555541"
        headers = {
            'cookie': self.cookie,
            'origin': 'https://study.163.com',
            'Content-Type': 'text/plain'
        }
        response = requests.request("POST", url, headers=headers, data=payload)
        res = response.text
        # print(res)
        try:
            signature = re.findall('signature="(.+?)"', res)[0]
            video_id = re.findall('videoId=(.+?);', res)[0]
            # print(f'video: {video_id}\nsignature: {signature}')
            return signature, video_id
        except BaseException as e:
            print(f'error:{e}\n可能是 cookie 过期')

    def get_video_info(self, lesson_id: str | int):
        """获取视频信息，用来构造下载地址"""
        signature, video_id = self.get_signature(lesson_id)
        if signature:
            url = f"https://vod.study.163.com/eds/api/v1/vod/video?videoId={video_id}&signature={signature}&clientType=1"
            response = requests.request("GET", url)
            res = response.json()
            if res['code'] == 0:
                videos = res['result']['videos']
                # print(videos)
                return videos

    def get_m3u8_url(self, lesson_id: str | int) -> str:
        """构造下载地址"""
        videos = self.get_video_info(lesson_id)
        # 这里是有多个视频信息的，根据特征，我目测最后一个是最高视频清晰度规格的，所以取 -1
        video_info = videos[-1]
        url_include_ak = video_info['videoUrl']
        k = video_info['k']
        token = study_163_k_decrypt_2_token(k)
        m3u8_url = f'{url_include_ak}&token={quote(token)}'
        # print(f'M3U8_URL:{m3u8_url}')
        # 返回构造完毕的 m3u8_url
        return m3u8_url

    def download_one_lesson(self, lesson_info: dict):
        # 下载单个课程的方法
        lesson_id = lesson_info['lesson_id']
        lesson_name = lesson_info['lesson_name']
        m3u8_url = self.get_m3u8_url(lesson_id)
        if not os.path.exists(self.save_dir_name):
            os.makedirs(self.save_dir_name)
        download_m3u8_video(m3u8_url, f'{self.save_dir_name}/{lesson_name}')

    def download_all_lessons(self, task_list=None):
        # 批量下载的方法，多写了一个方法，可以指定下载的任务，如果不指定，就是全局下载；
        if not task_list:
            task_list = self.get_lessons_list()
        print('任务数量：', len(task_list))
        with ThreadPoolExecutor() as executor:
            executor.map(self.download_one_lesson, task_list)


def main():
    ini_info = get_ini_config()
    course_id = ini_info["course_id"]
    save_name = ini_info["save_name"]
    study_sess = ini_info["study_sess"]
    cookies = f'STUDY_SESS="{ini_info["study_sess"]}";'
    if not all([course_id, save_name, study_sess]):
        input('参数不能为空，请检查 config.ini 文件的参数是有空值')
        return
    downloader = Downloader(cookies, course_id, save_name)
    downloader.download_all_lessons()
    input('【完成】:任务执行完成，按回车键退出程序')


if __name__ == '__main__':
    main()
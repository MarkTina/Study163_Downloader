import configparser


def get_ini_config(ini_filepath: str = 'config.ini') -> dict:
    # 创建一个ConfigParser对象
    config = configparser.ConfigParser()
    # 读取INI配置文件
    config.read(ini_filepath, encoding='utf-8')
    study_sess = config['args']['study_sess']
    course_id = config['args']['course_id']
    save_name = config['args']['save_name']
    return {
        'study_sess': study_sess,
        'course_id': course_id,
        'save_name': save_name
    }

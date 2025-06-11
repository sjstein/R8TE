import configparser

CONFIG_FILE = 'r8gpt.cfg'

RED_SQUARE = ':red_square:'
RED_EXCLAMATION = ':exclamation:'
GREEN_CIRCLE = ':green_circle:'

config = configparser.ConfigParser()
if len(config.read(CONFIG_FILE)) == 0:
    print(f'Error in loading configuration file "{CONFIG_FILE}" - does it exist? Is it empty?')
    exit(-1)

try:
    # Local configuration options
    USER_DB = config['local']['db_name']
    LOG_FILE = config['local']['log_file']
    DB_FILENAME = USER_DB + '.csv'
    LOG_FILENAME = LOG_FILE + '.log'

    # run8 specific options
    WORLDSAVE_PATH = config['run8']['world_save_path']

    # r8gpt options
    SCAN_TIME = int(config['r8gpt']['scan_time'])
    AI_ALERT_TIME = int(config['r8gpt']['ai_alert_time'])
    PLAYER_ALERT_TIME = int(config['r8gpt']['player_alert_time'])
    REMINDER_TIME = int(config['r8gpt']['reminder_time'])
    IGNORED_TAGS = [tag.strip().lower() for tag in config['r8gpt']['ignored_tags'].split(',')]
    REBOOT_TIME = int(config['r8gpt']['reboot_time'])

    # Discord options
    BOT_TOKEN = config['discord']['bot_token']
    CH_LOG = config['discord']['ch_log']
    if CH_LOG.lower() == 'none':
        CH_LOG = 'none'
    CH_ALERT = config['discord']['ch_alert']
    CREWED_TAG = config['discord']['crewed_tag']
    AVAILABLE_TAG = config['discord']['available_tag']
    COMPLETED_TAG = config['discord']['completed_tag']

    LOCATION_DB = {100: 'Mojave',
                   110: 'Needles',
                   120: 'Cajon',
                   130: 'Seligman',
                   140: 'CSX A-line',
                   150: 'Barstow/Yermo',
                   200: 'San Bernardino',
                   250: 'Bakersfield',
                   340: 'Modesto'}


except KeyError as e:
    print(f'\nr8dium ({__name__}.py): FATAL exception, unable to find [{e}] in configuration file')
    exit(-1)

except Exception as e:
    print(f'\nr8dium ({__name__}.py): FATAL exception type unknown - contact devs')
    exit(-1)
import configparser

CONFIG_FILE = 'r8gpt.cfg'

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
    AI_ALERT_TIME = int(config['r8gpt']['ai_alert_time'])
    PLAYER_ALERT_TIME = int(config['r8gpt']['player_alert_time'])

    # Discord options
    BOT_TOKEN = config['discord']['bot_token']
    CH_LOG = config['discord']['ch_log']
    if CH_LOG.lower() == 'none':
        CH_LOG = 'none'
    CH_ALERT = config['discord']['ch_alert']
    CREWED_TAG = config['discord']['crewed_tag']

except KeyError as e:
    print(f'\nr8dium ({__name__}.py): FATAL exception, unable to find [{e}] in configuration file')
    exit(-1)

except Exception as e:
    print(f'\nr8dium ({__name__}.py): FATAL exception type unknown - contact devs')
    exit(-1)
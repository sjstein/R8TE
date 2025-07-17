import configparser

CONFIG_FILE = 'r8gpt.cfg'

class Car:
    def __init__(self, filename, unit_type, route, track, node, dist, reverse, weight,
                 dest_tag, unit_number, hazmat_tag):
        self.filename = filename
        self.unit_type = unit_type
        self.route = route
        self.track = track
        self.node = node
        self.dist = dist
        self.reverse = reverse
        self.weight = weight
        self.dest_tag = dest_tag
        self.unit_number = unit_number
        self.hazmat_tag = hazmat_tag

    def __str__(self):
        return str(f'fname: {self.filename}, type: {self.unit_type}, route: {self.route}, track: {self.track}, '
                   f'node: {self.node}, dist: {self.dist}, reverse: {self.reverse}, weight: {self.weight}, '
                   f'dest_tag: {self.dest_tag}, unit_number: {self.unit_number}, hazmat: {self.hazmat_tag}')


class Cut:
    def __init__(self, train_id, is_ai, direction, speed_limit, prev_signal, consist):
        self.train_id = train_id
        self.is_ai = is_ai
        self.direction = direction
        self.speed_limit = speed_limit
        self.prev_signal = prev_signal
        self.consist = consist

    def __str__(self):
        return str(f'ID: {self.train_id}, AI: {self.is_ai}, dir: {self.direction}, spd limit {self.speed_limit},'
                   f'prev signal: {self.prev_signal}, # cars: {len(self.consist)} ')


class Train:
    def __init__(self, train_id, symbol, lead_num, train_type, num_units, engineer, consist,
                 last_time_moved, route, track, dist):
        self.train_id = train_id  # Unique ID
        self.symbol = symbol  # Train tag symbol
        self.lead_num = lead_num  # Lead loco number
        self.train_type = train_type  # freight, passenger
        self.num_units = num_units  # Number of locos + cars total
        self.engineer = engineer  # AI, player name, none
        self.consist = consist  # Full consist of train
        self.last_time_moved = last_time_moved  # Last time the train showed as moving
        self.route = route
        self.track = track
        self.dist = dist
        self.discord_id = ''  # Unique discord ID of player crewing this train
        self.job_thread = ''  # Keep track of thread where this train is being monitored

    def __str__(self):
        return str(f'ID: {self.train_id}\nSymbol: {self.symbol}\nLead#: {self.lead_num}\nType: {self.train_type}\n'
                   f'Number of cars:{self.num_units}\nEngineer: {self.engineer}\nRoute: {self.route}\n'
                   f'Track: {self.track}\nDist: {self.dist}\nLast Update: {self.last_time_moved}\n'
                   f'Discord id: {self.discord_id}\nJob thread: {self.job_thread}')


class Player:
    def __init__(self, discord_id, discord_name, job_thread, train_symbol, train_id, start_time):
        self.discord_id = discord_id
        self.discord_name = discord_name
        self.job_thread = job_thread
        self.train_symbol = train_symbol
        self.train_id = train_id
        self.start_time = start_time

    def __str__(self):
        return str(f'Discord id: {self.discord_id}\nDiscord name: {self.discord_name}\nJob thread: {self.job_thread}\n'
                   f'Train symbol: {self.train_symbol}\nTrain ID: {self.train_id}\nStart time: {self.start_time}')


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
    RED_SQUARE = f":{config['discord']['alert_emoji']}:"
    RED_EXCLAMATION = f":{config['discord']['reminder_emoji']}:"
    GREEN_CIRCLE = f":{config['discord']['moving_emoji']}:"
    AXE = f":{config['discord']['deleted_emoji']}:"

    LOCATION_DB = {100: 'Mojave',
                   110: 'Needles',
                   120: 'Cajon',
                   130: 'Seligman',
                   140: 'CSX A-line',
                   150: 'Barstow/Yermo',
                   170: 'Selkirk',
                   200: 'San Bernardino',
                   210: 'Waycross',
                   230: 'Fitzgerald',
                   240: 'Mohawk',
                   250: 'Bakersfield',
                   260: 'Roseville',
                   280: 'AGS South',
                   290: 'Pittsburgh East',
                   310: 'Arvin/Oak Creek',
                   320: 'Trona',
                   340: 'Modesto'}


except KeyError as e:
    print(f'\nr8dium ({__name__}.py): FATAL exception, unable to find [{e}] in configuration file')
    exit(-1)

except Exception as e:
    print(f'\nr8dium ({__name__}.py): FATAL exception type unknown - contact devs')
    exit(-1)
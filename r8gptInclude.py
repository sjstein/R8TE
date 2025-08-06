import configparser

CONFIG_FILE = 'r8gpt.cfg'


class Car:
    __slots__ = ('filename', 'unit_type', 'route_1', 'route_2', 'track_1', 'track_2', 'node_1', 'node_2',
                 'dist_1', 'dist_2', 'reverse_1', 'reverse_2', 'weight', 'dest_tag', 'unit_number', 'hazmat_index')

    def __init__(self,
                 filename: str,
                 unit_type: str,
                 route_1: int,
                 route_2: int,
                 track_1: int,
                 track_2: int,
                 node_1: int,
                 node_2: int,
                 dist_1: float,
                 dist_2: float,
                 reverse_1: bool,
                 reverse_2: bool,
                 weight: float,
                 dest_tag: str,
                 unit_number: int,
                 hazmat_index: int
                 ):

        self.filename = str(filename)
        self.unit_type = str(unit_type)
        self.route_1 = int(route_1)
        if route_2:
            self.route_2 = int(route_2)
        else:
            self.route_2 = route_2
        self.track_1 = int(track_1)
        if track_2:
            self.track_2 = int(track_2)
        else:
            self.track_2 = track_2
        self.node_1 = int(node_1)
        if node_2:
            self.node_2 = int(node_2)
        else:
            self.node_2 = node_2
        self.dist_1 = float(dist_1)
        if dist_2:
            self.dist_2 = float(dist_2)
        else:
            self.dist_2 = dist_2
        self.reverse_1 = bool(reverse_1)
        if reverse_2:
            self.reverse_2 = bool(reverse_2)
        else:
            self.reverse_2 = reverse_2
        self.weight = float(weight)
        self.dest_tag = str(dest_tag)
        self.unit_number = int(unit_number)
        self.hazmat_index = int(hazmat_index)

    def __str__(self):
        return str(f'fname: {self.filename}, type: {self.unit_type}, route: ({self.route_1}, {self.route_2}), '
                   f'track: ({self.track_1}, {self.track_2}), node: ({self.node_1}, {self.node_2}), '
                   f'dist: ({self.dist_1}, {self.dist_2}), reverse: ({self.reverse_1}, {self.reverse_2}), ' 
                   f'weight: {self.weight}, dest_tag: {self.dest_tag}, unit_number: {self.unit_number}, '
                   f'hazmat: {self.hazmat_index}')


class Cut:
    __slots__ = ('train_id', 'is_ai', 'direction', 'speed_limit', 'prev_signal', 'consist')

    def __init__(self,
                 train_id: int,
                 is_ai: str,
                 direction: int,
                 speed_limit: int,
                 prev_signal: str,
                 consist: list
                 ):

        self.train_id = int(train_id)
        if is_ai.lower() == 'true':
            self.is_ai = True
        else:
            self.is_ai = False
        self.direction = int(direction)
        self.speed_limit = int(speed_limit)
        self.prev_signal = str(prev_signal)
        self.consist = consist

    def __str__(self):
        return str(f'ID: {self.train_id}, AI: {self.is_ai}, dir: {self.direction}, spd limit {self.speed_limit},'
                   f'prev signal: {self.prev_signal}, # cars: {len(self.consist)} ')


class Train:

    __slots__ = ('train_id', 'symbol', 'lead_num', 'train_type', 'num_units', 'engineer', 'consist', 'last_time_moved',
                 'route_1', 'route_2', 'track_1', 'track_2', 'dist_1', 'dist_2', 'discord_id', 'job_thread')
    def __init__(self,
                 train_id: int,
                 symbol: str,
                 lead_num: int,
                 train_type: str,
                 num_units: int,
                 engineer: str,
                 consist: list,
                 last_time_moved,
                 route_1: int,
                 route_2: int,
                 track_1: int,
                 track_2: int,
                 dist_1: float,
                 dist_2: float
                 ):
        self.train_id = int(train_id)  # Unique ID
        self.symbol = str(symbol)  # Train tag symbol
        self.lead_num = int(lead_num)  # Lead loco number
        self.train_type = str(train_type)  # freight, passenger
        self.num_units = int(num_units)  # Number of locos + cars total
        self.engineer = str(engineer)  # AI, player name, none
        self.consist = consist  # Full consist of train
        self.last_time_moved = last_time_moved  # Last time the train showed as moving
        self.route_1 = int(route_1)
        if route_2:
            self.route_2 = int(route_2)
        else:
            self.route_2 = route_2
        self.track_1 = int(track_1)
        if track_2:
            self.track_2 = int(track_2)
        else:
            self.track_2 = track_2
        self.dist_1 = float(dist_1)
        if dist_2:
            self.dist_2 = float(dist_2)
        else:
            self.dist_2 = dist_2
        self.discord_id = ''  # Unique discord ID of player crewing this train
        self.job_thread = ''  # Keep track of thread where this train is being monitored

    def __str__(self):
        return str(f'ID: {self.train_id}\nSymbol: {self.symbol}\nLead#: {self.lead_num}\nType: {self.train_type}\n'
                   f'Number of cars:{self.num_units}\nEngineer: {self.engineer}\nRoute: {self.route_1}\n'
                   f'Track: {self.track_1}\nDist: {self.dist_1}, {self.dist_2}\nLast Update: {self.last_time_moved}\n'
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

class CarReport:
    def __init__(self, type, dir, seq, road, nbr, loaded, wt, hazmat, tag, defect, filename):
        self.type = type
        self.dir = dir
        self.seq = seq
        self.road = road
        self.nbr = nbr
        self.loaded = loaded
        self.wt = wt
        self.hazmat = hazmat
        self.tag = tag
        self.defect = defect
        self.filename = filename

    def __str__(self):
        msg = (f'{self.type}\n{self.dir}\n{self.seq}\n{self.road}\n{self.nbr}\n{self.loaded}\n{self.wt}\n'
               f'{self.hazmat}\n{self.tag}\n{self.defect}\n{self.filename}')
        return msg

class AeiReport:
    def __init__(self, name, timestamp, symbol, speed, axles, loads, empties, tons, length, units):
        self.name = name
        self.timestamp = timestamp
        self.symbol = symbol
        self.speed = int(speed)
        self.axles = int(axles)
        self.loads = int(loads)
        self.empties = int(empties)
        self.tons = int(tons)
        self.length = int(length)
        self.units = units

    def __str__(self):
        msg = (f'Detector : {self.name}\nTime: {self.timestamp}\nTrain ID : {self.symbol}\nSpeed : {self.speed}\n'
               f'Total Axles : {self.axles}\nWeight (tons): {self.tons}\nLength (feet) : {self.length}\nDefects :')
        no_defect = True
        for unit in self.units:
            if unit.defect.lower() != 'all_ok':
                no_defect = False
                msg += f'{unit.seq} : {unit.defect}\n'
            # msg += f'{unit}\n----\n'
        if no_defect:
            msg += 'None\n'
        return msg

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
    AEI_PATH = config['run8']['aei_path']

    # r8gpt options
    SCAN_TIME = int(config['r8gpt']['scan_time'])
    AI_ALERT_TIME = int(config['r8gpt']['ai_alert_time'])
    PLAYER_ALERT_TIME = int(config['r8gpt']['player_alert_time'])
    REMINDER_TIME = int(config['r8gpt']['reminder_time'])
    IGNORED_TAGS = [tag.strip().lower() for tag in config['r8gpt']['ignored_tags'].split(',')]
    REBOOT_TIME = int(config['r8gpt']['reboot_time'])
    temp = config['r8gpt']['track_ai_detectors']
    if temp.lower() == 'true':
        TRACK_AI_DD = True
    else:
        TRACK_AI_DD = False

    # Discord options
    BOT_TOKEN = config['discord']['bot_token']
    CH_LOG = config['discord']['ch_log']
    if CH_LOG.lower() == 'none':
        CH_LOG = 'none'
    CH_ALERT = config['discord']['ch_alert']
    CH_DETECTOR = config['discord']['ch_detector']
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

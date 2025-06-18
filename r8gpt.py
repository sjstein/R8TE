import asyncio
from collections import defaultdict
import discord
from discord.ext import tasks
from discord import option
from discord.errors import HTTPException
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta
import os
from r8gptInclude import (WORLDSAVE_PATH, DB_FILENAME, LOG_FILENAME, AI_ALERT_TIME, PLAYER_ALERT_TIME, REMINDER_TIME,
                          BOT_TOKEN, CH_LOG, CH_ALERT, CREWED_TAG, COMPLETED_TAG, AVAILABLE_TAG, LOCATION_DB,
                          SCAN_TIME, IGNORED_TAGS, REBOOT_TIME, RED_SQUARE, RED_EXCLAMATION, GREEN_CIRCLE, AXE)
import r8gptDB

DEBUG = True

# Necessary Bot intents
intents = discord.Intents.default()
intents.guilds = True
intents.messages = True
intents.message_content = True

SAVENAME = WORLDSAVE_PATH + '/Auto Save World.xml'
DIESEL_ENGINE = 'US_DieselEngine'
DISCORD_CHAR_LIMIT = 2000
TMP_FILENAME = 'r8gpt_msg.txt'

event_db = list()


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
    def __init__(self, id_number, symbol, lead_num, train_type, num_units, engineer, consist,
                 last_time_moved, route, track, dist):
        self.id_number = id_number  # Unique ID
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
        self.discord_name = ''  # Human readable player name (if needed)
        self.job_thread = ''  # Keep track of thread where this train is being monitored

    def __str__(self):
        return str(f'ID: {self.id_number}\nSymbol: {self.symbol}\nLead#: {self.lead_num}\nType: {self.train_type}\n'
                   f'Number of cars:{self.num_units}\nEngineer: {self.engineer}\nRoute: {self.route}\n'
                   f'Track: {self.track}\nDist: {self.dist}\nLast Update: {self.last_time_moved}')


def parse_train_loader(root):
    cuts = list()
    for t in root.iter('TrainLoader'):
        train_id = t.find('trainID').text
        was_ai = t.find('TrainWasAI').text
        direction = t.find('DispatchTrainDirection').text
        speed_limit = t.find('ManuallyAppliedSpeedLimitMPH').text
        prev_signal = t.find('PreviousSignalInstruction').text
        units = list()
        unitLoader = t.find('unitLoaderList')
        for rail_vehicle in unitLoader.iter('RailVehicleStateClass'):
            file_name = rail_vehicle.find('rvXMLfilename').text
            unit_type = rail_vehicle.find('unitType').text
            if len(rail_vehicle.find("currentRoutePrefix")) > 1:
                route_prefix = (rail_vehicle.find('currentRoutePrefix')[0].text,
                                rail_vehicle.find('currentRoutePrefix')[1].text)
                track_index = (rail_vehicle.find('currentTrackSectionIndex')[0].text,
                               rail_vehicle.find('currentTrackSectionIndex')[1].text)
                start_node = (rail_vehicle.find('startNodeIndex')[0].text,
                              rail_vehicle.find('startNodeIndex')[1].text)
                distance = (rail_vehicle.find('distanceTravelledInMeters')[0].text,
                            rail_vehicle.find('distanceTravelledInMeters')[1].text)
                reverse = (rail_vehicle.find('reverseDirection')[0].text,
                           rail_vehicle.find('reverseDirection')[1].text)
            else:
                route_prefix = rail_vehicle.find('currentRoutePrefix')[0].text
                track_index = rail_vehicle.find('currentTrackSectionIndex')[0].text
                start_node = rail_vehicle.find('startNodeIndex')[0].text
                distance = rail_vehicle.find('distanceTravelledInMeters')[0].text
                reverse = rail_vehicle.find('reverseDirection')[0].text
            load_weight = rail_vehicle.find('loadWeightUSTons').text
            dest_tag = rail_vehicle.find('destinationTag').text
            unit_number = rail_vehicle.find('unitNumber').text
            hazmat_tag = rail_vehicle.find('hazmatPlacardIndex').text
            units.append(
                Car(file_name, unit_type, route_prefix, track_index, start_node, distance, reverse, load_weight,
                    dest_tag, unit_number, hazmat_tag))
        cuts.append(Cut(train_id, was_ai, direction, speed_limit, prev_signal, units.copy()))
        units.clear()
    return cuts


def location(route_id, track_index):
    sub = int(route_id[0])
    trk = int(track_index[0])

    return LOCATION_DB[sub], trk


trains = dict()  # Dict of all trains in the world
latest_trains = dict()  # Dict of latest update of trains in the world
player_list = dict()  # Dict of player controlled trains
watched_trains = dict()  # Dict of trains which are stalled/stuck
alert_messages = defaultdict(list)  # Dict of messages sent to alert channel

global fp  # File pointer to log
global last_world_datetime


def update_world_state():
    global trains

    trains.clear()
    tree = ET.parse(SAVENAME)
    root = tree.getroot()
    world_save_datetime = datetime.strptime(root.find('date').text.split('.')[0], '%Y-%m-%dT%H:%M:%S')
    cuts = parse_train_loader(root)
    for cut in cuts:
        if cut.consist[0].unit_type == DIESEL_ENGINE:  # We are only interested in consists with lead locos
            tid = cut.train_id
            tag = cut.consist[0].dest_tag
            nbr = cut.consist[0].unit_number
            rp = cut.consist[0].route
            ts = cut.consist[0].track
            dist = cut.consist[0].dist
            if 'amtrak' in cut.consist[0].filename.lower():
                train_type = 'Passenger'
            else:
                train_type = 'Freight'
            if cut.is_ai.lower() == 'true':
                trains[tid] = Train(tid, tag, nbr, train_type, len(cut.consist), 'AI', cut.consist.copy(),
                                    world_save_datetime, rp, ts, dist)
            elif tid in {value: key for key, value in player_list.items()}:
                player_id = [key for key, val in player_list.items() if val == tid]
                trains[tid] = Train(tid, tag, nbr, train_type, len(cut.consist),
                                    player_id[0], cut.consist.copy(), world_save_datetime, rp, ts, dist)
            else:
                trains[tid] = Train(tid, tag, nbr, train_type, len(cut.consist),
                                    'None', cut.consist.copy(), world_save_datetime, rp, ts, dist)
        else:
            # First car is not a locomotive, so not a valid train
            pass
    return world_save_datetime


def find_tid(train_tag):
    global trains
    # Return tid for a given train symbol to be taken over by player
    for tid in trains:
        if trains[tid].symbol.lower() == train_tag.lower():
            return tid
    return -1


def train_count(train_type):
    global trains
    count = 0
    if train_type.lower() == 'ai':
        for tid in trains:
            if trains[tid].engineer.lower() == 'ai':
                count += 1
    elif train_type.lower() == 'player':
        for tid in trains:
            if trains[tid].engineer.lower() != 'none' and trains[tid].engineer.lower() != 'ai':
                count += 1
    elif train_type.lower() == 'stuck':
        count = len(watched_trains)
    elif train_type.lower() == 'all':
        count = len(trains)
    else:
        count = -1

    return count


def player_crew_train(tid, player_id, display_name, thread, add_time):
    global trains
    if tid not in player_list:
        player_list[player_id] = tid
        trains[tid].engineer = player_id
        trains[tid].discord_name = display_name
        trains[tid].job_thread = thread
        trains[tid].last_time_moved = add_time


def del_player_train(tid, player_id):
    global trains
    if player_id in player_list and player_list[player_id] == tid:
        del player_list[player_id]
        trains[tid].engineer = 'None'


def log_msg(msg):
    global fp

    fp = open(LOG_FILENAME, 'a')
    fp.write(msg + '\n')
    fp.close()


bot = discord.Bot(intents=intents)


@bot.slash_command(name='crew', description=f"Crew a train")
@option("symbol", description="Train symbol", required=True)
# NOTE: This command must be executed within a forum thread
async def crew(ctx: discord.ApplicationContext, symbol: str):
    global last_world_datetime

    thread = ctx.channel
    thread_id = ctx.channel.id
    forum_channel = thread.parent
    tag_to_add = discord.utils.find(lambda t: t.name.lower() == CREWED_TAG.lower(), forum_channel.available_tags)
    tag_to_remove = discord.utils.find(lambda t: t.name.lower() == AVAILABLE_TAG.lower(), forum_channel.available_tags)
    if not tag_to_add or not tag_to_remove:
        await ctx.respond(f'[r8GPT] **ERROR**: Tag `{CREWED_TAG}` and/or {AVAILABLE_TAG} not found in this forum.'
                          , ephemeral=True)
        return
    current_tags = thread.applied_tags or []
    if tag_to_add in current_tags:
        await ctx.respond(f'This job is already marked `{tag_to_add.name}` - unable to crew.', ephemeral=True)
        return
    try:
        await ctx.respond(f'Attempting to crew train {symbol}', ephemeral=True)
        tid = find_tid(symbol)
        if tid != -1:
            if trains[tid].engineer == 'None':
                player_crew_train(tid, ctx.author.mention, ctx.author.display_name, thread_id, last_world_datetime)
                if tag_to_add not in current_tags:
                    current_tags.append(tag_to_add)
                if tag_to_remove in current_tags:
                    current_tags.remove(tag_to_remove)
                msg = f'[{trains[tid].last_time_moved}] {ctx.author.display_name} crewed {trains[tid].symbol}'
                await thread.edit(applied_tags=current_tags)
                log_msg(msg)
                r8gptDB.add_event(trains[tid].last_time_moved, ctx.author.display_name,
                                  'CREW', symbol, event_db)
                r8gptDB.save_db(DB_FILENAME, event_db)
                await thread.send(msg)
            else:
                await ctx.respond(f'**UNABLE TO CREW, Train {symbol} shows '
                                  f'crewed by {trains[tid].engineer}**', ephemeral=True)
        else:
            await ctx.respond(f'**UNABLE TO CREW, Train {symbol} not found**')
    except discord.Forbidden:
        await ctx.respond('[r8GPT] **ERROR**: I do not have permission to edit this thread.', ephemeral=True)
    except Exception as e:
        await ctx.respond(f'[r8GPT] **ERROR**: {e}', ephemeral=True)


@bot.slash_command(name='tie_down', description=f"Tie down a train")
@option("location", description="Tie-down location", required=True)
async def tie_down(ctx: discord.ApplicationContext, location: str):
    thread = ctx.channel
    if not isinstance(thread, discord.Thread) or not isinstance(thread.parent, discord.ForumChannel):
        await ctx.respond('This command must be used inside a forum thread.', ephemeral=True)
        return
    forum_channel = thread.parent
    tag_to_add = discord.utils.find(lambda t: t.name.lower() == AVAILABLE_TAG.lower(), forum_channel.available_tags)
    tag_to_remove = discord.utils.find(lambda t: t.name.lower() == CREWED_TAG.lower(), forum_channel.available_tags)
    if not tag_to_add or not tag_to_remove:
        await ctx.respond(f'[r8GPT] **ERROR**: Tag `{CREWED_TAG}` and/or `{AVAILABLE_TAG}` not found in this forum.'
                          , ephemeral=True)
    current_tags = thread.applied_tags or []
    if tag_to_remove not in current_tags:
        await ctx.respond(f'Tag **{tag_to_remove.name}** is not currently applied.', ephemeral=True)
        return
    try:
        await ctx.respond(f'Attempting to tie down', ephemeral=True)
        for tid in trains:
            if trains[tid].engineer == ctx.author.mention:
                if tid in watched_trains:
                    watched_trains.pop(tid)
                del_player_train(tid, ctx.author.mention)
                if tag_to_add not in current_tags:
                    current_tags.append(tag_to_add)
                if tag_to_remove in current_tags:
                    current_tags.remove(tag_to_remove)
                msg = (f'[{trains[tid].last_time_moved}] {ctx.author.display_name} tied down train '
                       f'{trains[tid].symbol} at {location}')
                await thread.send(msg)
                await thread.edit(applied_tags=current_tags)
                log_msg(msg)
                r8gptDB.add_event(trains[tid].last_time_moved, ctx.author.display_name,
                                  'TIED_DOWN', trains[tid].symbol, event_db)
                r8gptDB.save_db(DB_FILENAME, event_db)
                return
        else:
            await ctx.respond(f'**ERROR** Unable to tie-down: '
                              f'You are not listed as crew on any train.', ephemeral=True)

    except discord.Forbidden:
        await ctx.respond('[r8GPT] does not have permission to edit this thread.', ephemeral=True)
    except Exception as e:
        await ctx.respond(f'[r8GPT] Unexpected error: {e}', ephemeral=True)


@bot.slash_command(name='complete', description=f"Mark a job complete")
@option("symbol", description="Train symbol", required=True)
@option('notes', description='completion notes', required=False)
# NOTE: This command must be executed within a forum thread
async def complete(ctx: discord.ApplicationContext, symbol: str, notes: str):
    thread = ctx.channel
    if not isinstance(thread, discord.Thread) or not isinstance(thread.parent, discord.ForumChannel):
        await ctx.respond('This command must be used inside a forum thread.', ephemeral=True)
        return
    forum_channel = thread.parent
    tag_to_add = discord.utils.find(lambda t: t.name.lower() == COMPLETED_TAG.lower(), forum_channel.available_tags)
    tag1_to_remove = discord.utils.find(lambda t: t.name.lower() == CREWED_TAG.lower(), forum_channel.available_tags)
    tag2_to_remove = discord.utils.find(lambda t: t.name.lower() == AVAILABLE_TAG.lower(), forum_channel.available_tags)
    if not tag_to_add or not tag1_to_remove or not tag2_to_remove:
        await ctx.respond(f'[r8GPT] **ERROR**: Tag `{CREWED_TAG}` and/or `{AVAILABLE_TAG}` and/or {COMPLETED_TAG}'
                          f' not found in this forum.', ephemeral=True)
        return
    current_tags = thread.applied_tags or []
    if tag_to_add in current_tags:
        await ctx.respond(f'This job is already marked `{tag_to_add.name}` - unable to change.', ephemeral=True)
        return
    try:
        await ctx.respond(f'Attempting to mark {symbol} as complete.', ephemeral=True)
        for train in trains:
            if trains[train].engineer == ctx.author.mention:
                if trains[train].symbol.lower() == symbol.lower():
                    del_player_train(train, ctx.author.mention)
                    if tag_to_add not in current_tags:
                        current_tags.append(tag_to_add)
                    if tag1_to_remove in current_tags:
                        current_tags.remove(tag1_to_remove)
                    if tag2_to_remove in current_tags:
                        current_tags.remove(tag2_to_remove)
                    msg = (f'[{trains[train].last_time_moved}] {ctx.author.display_name} marked train '
                           f'{trains[train].symbol} {COMPLETED_TAG}')
                    if len(notes) > 0:
                        msg += f'. Notes: {notes}'
                    await thread.send(msg)
                    await thread.edit(applied_tags=current_tags)
                    log_msg(msg)
                    r8gptDB.add_event(trains[train].last_time_moved, ctx.author.display_name,
                                      'MARKED_COMPLETE', trains[train].symbol, event_db)
                    r8gptDB.save_db(DB_FILENAME, event_db)
                    return
                else:
                    await ctx.respond(f'Unable to mark {symbol} as complete,'
                                      f' it appears you are crewing {player_list[ctx.author.mention]}', ephemeral=True)
        else:
            await ctx.respond(f'Unable to mark as complete; are you sure you are clocked in?', ephemeral=True)
    except discord.Forbidden:
        await ctx.respond('[r8GPT] **ERROR**: I do not have permission to edit this thread.', ephemeral=True)
    except Exception as e:
        await ctx.respond(f'[r8GPT] **ERROR**: {e}', ephemeral=True)


@bot.slash_command(name="r8list", description="List trains")
@option('list_type', description='type of list (ai, player, idle, stuck)', required=True)
async def r8list(ctx: discord.ApplicationContext, list_type: str):
    msg = ''
    for tid in trains:
        if list_type.lower() == 'ai':
            if trains[tid].engineer.lower() == 'ai':
                msg += (f'{trains[tid].symbol} [{tid}] # {trains[tid].lead_num},'
                        f' Units: {trains[tid].num_units}\n')
        elif list_type.lower() == 'player':
            if trains[tid].discord_name:
                msg += (f'{trains[tid].discord_name} : {trains[tid].symbol} [{tid}] # {trains[tid].lead_num},'
                        f' Units: {trains[tid].num_units}\n')
        elif list_type.lower() == 'stuck':
            if tid in watched_trains:
                td = last_world_datetime - trains[tid].last_time_moved
                if trains[tid].engineer.lower() != 'ai':
                    msg += f'{trains[tid].discord_name}'
                else:
                    msg += f'{trains[tid].engineer}'
                msg += (f' : {trains[tid].symbol} [{tid}] # {trains[tid].lead_num},'
                        f' # {trains[tid].lead_num}, Units: {trains[tid].num_units}, Stopped for: {td},'
                        f' Location: {location(trains[tid].route, trains[tid].track)}\n')
        else:
            if trains[tid].engineer.lower() == 'none':
                msg += (f'{trains[tid].symbol} [{tid}] # {trains[tid].lead_num},'
                        f' Units: {trains[tid].num_units}\n')
    if len(msg) < 1:
        msg = f'No {list_type} trains found.'
    if len(msg) > DISCORD_CHAR_LIMIT:
        tf = open(TMP_FILENAME, 'w')
        tf.write(msg)
        tf.close()
        await ctx.response.send_message(file=discord.File(TMP_FILENAME), ephemeral=True)
    else:
        await ctx.respond(msg, ephemeral=True)
    # await ctx.respond(msg, ephemeral=True)


@bot.slash_command(name='train_info', description="Display info of individual train")
@option('tid', required=True, description='Train ID')
async def train_info(ctx: discord.ApplicationContext, tid: str):
    if tid in trains:
        msg = (f'{trains[tid].engineer} : {trains[tid].symbol} [{tid}]'
               f' # {trains[tid].lead_num}, total cars: {trains[tid].num_units}, last move:'
               f' {trains[tid].last_time_moved}\n')
    else:
        msg = f'Train {tid} not found.'
    await ctx.respond(msg, ephemeral=True)


@tasks.loop(seconds=SCAN_TIME)
async def scan_world_state():
    global fp
    global last_world_datetime
    global trains
    global last_modified  # designated global to keep track between calls

    async def send_ch_msg(ch_name, ch_msg):
        """
        Send messages to discord channel
        :param ch_name: name of discord channel to write message to
        :param ch_msg: Message content
        :return: 0 if successful, -1 if error
        """
        if ch_msg.lower() == 'none':
            return 0

        if len(ch_msg) > DISCORD_CHAR_LIMIT - 100:
            ch_msg = ch_msg[:DISCORD_CHAR_LIMIT - 100] + '[...truncated...]'

        for guild in bot.guilds:
            if type(ch_name) == str:
                for channel in guild.text_channels + guild.forum_channels:
                    threads = channel.threads
                    for thread in threads:
                        if thread.name.lower() == ch_name.lower():
                            # write to matching thread name
                            try:
                                retval = await thread.send('[r8GPT] ' + ch_msg)

                            except Exception as e:
                                print(f"Error in scan_world_state/send_ch_msg(1): {e}")

                            log_msg(ch_msg)
                            return retval

                    if channel.name.lower() == ch_name.lower():
                        # Write to a matching channel name
                        try:
                            retval = await channel.send('[r8GPT] ' + ch_msg)
                        except Exception as e:
                            print(f"Error in scan_world_state/send_ch_msg(2): {e}")

                        log_msg(ch_msg)
                        return retval
            else:
                try:
                    retval = await ch_name.send('[r8GPT] ' + ch_msg)

                except Exception as e:
                    print(f"Error in scan_world_state/send_ch_msg(1): {e}")

                log_msg(ch_msg)
                return retval

        print(f"[Warning] thread / channel {ch_name} not found.")
        return -1

    if len(trains) == 0:  # No trains means we need to read initial state
        last_modified = os.stat(SAVENAME).st_mtime  # Time
        last_world_datetime = update_world_state()
        msg = (f'** {last_world_datetime} Initializing ** '
               f'Total number of trains: {train_count("all")} (AI trains: {train_count("ai")},'
               f' player trains: {train_count("player")}) ')
        print(msg)
        await send_ch_msg(CH_LOG, msg)

    elif (os.stat(SAVENAME).st_mtime - last_modified) > REBOOT_TIME:
        await send_ch_msg(CH_LOG, '**Apparent server reboot** : Re-syncing train states')

        # Look for and archive player trains
        # Capture existing player records
        player_updates = list()
        for pid in player_list:
            tid = player_list[pid]
            player_updates.append([trains[tid].engineer, trains[tid].discord_name,
                                   trains[tid].symbol, trains[tid].job_thread])
        player_list.clear()
        # Repopulate trains
        last_modified = os.stat(SAVENAME).st_mtime  # Time
        last_world_datetime = update_world_state()
        # Re-add players
        for player in player_updates:
            player_crew_train(find_tid(player[2]), player[0], player[1], player[3], last_world_datetime)
        player_updates.clear()
        watched_trains.clear()

        msg = (f'** {last_world_datetime} Initializing ** '
               f'Total number of trains: {train_count("all")} (AI trains: {train_count("ai")},'
               f' player trains: {train_count("player")}) ')
        print(msg)
        await send_ch_msg(CH_LOG, msg)

    if os.stat(SAVENAME).st_mtime != last_modified:  # Has file timestamp changed since last iteration?
        last_modified = os.stat(SAVENAME).st_mtime
        last_trains = trains.copy()  # Archive our current set of trains for comparison
        last_world_datetime = update_world_state()  # Update the trains dictionary

        # Check to see if any trains have been deleted
        nbr_ai_removed = 0
        trains_removed = list()

        for tid in last_trains:
            if tid not in trains:
                trains_removed.append(tid)
                nbr_ai_removed += 1
                msg = (f'{last_world_datetime} Train removed: {last_trains[tid].symbol} [{last_trains[tid].engineer}]'
                       f' (# {tid})')
                await send_ch_msg(CH_LOG, msg)
                await asyncio.sleep(.5)

                print(msg)
                if tid in watched_trains:
                    for msg in alert_messages[tid]:  # Change previous alerts
                        await msg.delete()  # Delete message
                    msg = (f' {AXE} {last_world_datetime} **TRAIN DELETED**:'
                           f' [{last_trains[tid].engineer}] {last_trains[tid].symbol} ({tid}) has been deleted.')
                    await send_ch_msg(CH_ALERT, msg)
                    await asyncio.sleep(.5)

                    del alert_messages[tid]
                    del watched_trains[tid]

            elif trains[tid].symbol != last_trains[tid].symbol:
                print(f'{last_world_datetime} Train re-tagged: {tid} has changed tags since last update '
                      f'({last_trains[tid].symbol} -> {trains[tid].symbol}); Updating record.')

        nbr_ai_moving = 0
        nbr_player_moving = 0
        nbr_ai_stopped = 0
        nbr_ai_added = 0
        nbr_player_stopped = 0

        for tid in trains:
            # Check for new trains
            if tid not in last_trains:
                nbr_ai_added += 1
                msg = f'{last_world_datetime} Train spawned: {trains[tid].symbol} ({tid})'
                print(msg)
                await send_ch_msg(CH_LOG, msg)
                await asyncio.sleep(.5)
            # Check for moving AI or player trains
            elif (trains[tid].engineer.lower() != 'none' and not
            any(tag in trains[tid].symbol.lower() for tag in IGNORED_TAGS)):  # Ignore static and special tags
                if (trains[tid].route != last_trains[tid].route
                        or trains[tid].track != last_trains[tid].track
                        or trains[tid].dist != last_trains[tid].dist):
                    # train HAS MOVED since last update
                    if trains[tid].engineer.lower() == 'ai':
                        nbr_ai_moving += 1
                    else:
                        nbr_player_moving += 1
                        trains[tid].discord_name = last_trains[tid].discord_name
                    if tid in watched_trains:
                        msg = (f' {GREEN_CIRCLE} {last_world_datetime} **ON THE MOVE**: Train {trains[tid].symbol}'
                               f' ({tid}) is now on the move after'
                               f' {last_world_datetime - last_trains[tid].last_time_moved}.')
                        await send_ch_msg(CH_ALERT, msg)
                        await asyncio.sleep(.5)
                        log_msg(msg)
                        for msg in alert_messages[tid]:  # Change previous alerts
                            if msg.content[10] == 'r':  # Message has the red square
                                new_msg = f'~~{msg.content[22:]}~~'  # Put a strikethru on previous message
                            else:  # Message has the red exclamation
                                new_msg = f'~~{msg.content[23:]}~~'
                            await msg.edit(content=new_msg)
                        del alert_messages[tid]
                        del watched_trains[tid]  # No longer need to watch
                elif (trains[tid].route == last_trains[tid].route
                      and trains[tid].track == last_trains[tid].track
                      and trains[tid].dist == last_trains[tid].dist):
                    # train HAS NOT MOVED since last update
                    if trains[tid].engineer.lower() == 'ai':
                        nbr_ai_stopped += 1
                    else:
                        nbr_player_stopped += 1
                        trains[tid].discord_name = last_trains[tid].discord_name
                        trains[tid].job_thread = last_trains[tid].job_thread
                    td = last_world_datetime - last_trains[tid].last_time_moved
                    sub = LOCATION_DB[int(trains[tid].route[0])]
                    if (trains[tid].engineer.lower() == 'ai' and td > timedelta(minutes=AI_ALERT_TIME) or
                            trains[tid].engineer.lower() != 'ai' and td > timedelta(minutes=PLAYER_ALERT_TIME)):
                        if tid not in watched_trains:
                            watched_trains[tid] = [trains[tid].last_time_moved, 1]
                            log_msg(f'Added {tid}: {trains[tid].symbol} to watched trains')
                            if trains[tid].engineer.lower() == 'ai':
                                msg = f' {RED_SQUARE} {last_world_datetime} **POSSIBLE STUCK TRAIN**: '
                                msg += (f' [{trains[tid].engineer}] {trains[tid].symbol} ({tid})'
                                        f' has not moved for {td}, '
                                        f'Location: {location(trains[tid].route, trains[tid].track)}.')
                                alert_messages[tid].append(await send_ch_msg(CH_ALERT, msg))
                            else:
                                alert_msg = f' {RED_SQUARE} {last_world_datetime} **POSSIBLE STUCK TRAIN**: '
                                alert_msg += (f' [{trains[tid].discord_name}] {trains[tid].symbol} ({tid})'
                                              f' has not moved for {td}, '
                                              f'Location: {location(trains[tid].route, trains[tid].track)}.')
                                alert_messages[tid].append(await send_ch_msg(CH_ALERT, alert_msg))
                                await asyncio.sleep(.5)
                                player_msg = (f'{trains[tid].engineer}: You are currently crewing {trains[tid].symbol},'
                                              f' yet your train has not moved for at least {td}. Should you tie down?')
                                forum_thread = await bot.fetch_channel(trains[tid].job_thread)
                                alert_messages[tid].append(await send_ch_msg(forum_thread, player_msg))
                            await asyncio.sleep(.5)
                        elif ((trains[tid].last_time_moved - watched_trains[tid][0])
                              // watched_trains[tid][1] > timedelta(minutes=REMINDER_TIME)):
                            watched_trains[tid][1] += 1
                            if trains[tid].engineer.lower() == 'ai':
                                msg = (f' {RED_EXCLAMATION} {last_world_datetime}'
                                       f' **STUCK TRAIN REMINDER # {watched_trains[tid][1] - 1}**: ')
                                msg += (f'[{trains[tid].engineer}] {trains[tid].symbol} ({tid})'
                                        f' has not moved for {td}, '
                                        f'Location: {location(trains[tid].route, trains[tid].track)}.')
                                alert_messages[tid].append(await send_ch_msg(CH_ALERT, msg))
                                await asyncio.sleep(.5)
                            else:
                                alert_msg = (f' {RED_EXCLAMATION} {last_world_datetime} **STUCK TRAIN REMINDER #'
                                             f' {watched_trains[tid][1] - 1}**: ')
                                alert_msg += (f' [{trains[tid].discord_name}] {trains[tid].symbol} ({tid})'
                                              f' has not moved for {td}, '
                                              f'Location: {location(trains[tid].route, trains[tid].track)}.')
                                alert_messages[tid].append(await send_ch_msg(CH_ALERT, alert_msg))
                                await asyncio.sleep(.5)
                                player_msg = (f'{trains[tid].engineer}: You are currently crewing {trains[tid].symbol},'
                                              f' yet your train has not moved for at least {td}. Should you tie down?')
                                forum_thread = await bot.fetch_channel(trains[tid].job_thread)
                                alert_messages[tid].append(await send_ch_msg(forum_thread, player_msg))
                        else:
                            pass  # We have already notified at least once, now backing off before another notice
                    print(f'[{trains[tid].engineer}] {trains[tid].symbol} ({tid}) has not moved for {td}, '
                          f'Location: {location(trains[tid].route, trains[tid].track)}')
                    trains[tid].last_time_moved = last_trains[tid].last_time_moved
                    trains[tid].job_thread = last_trains[tid].job_thread
                else:
                    print(f'something odd in comparing these two:\n{trains[tid]}\n{last_trains[tid]}')

        msg = (f'{last_world_datetime} Summary: AI ({nbr_ai_moving}M, {nbr_ai_stopped}S, +{nbr_ai_added}, '
               f'-{nbr_ai_removed}) | Player ({nbr_player_moving}M, {nbr_player_stopped}S) | '
               f'Watched ({len(watched_trains)})')

        await send_ch_msg(CH_LOG, msg)
        await asyncio.sleep(.5)
        print(msg)


@bot.event
async def on_ready():
    global fp
    global event_db

    print(f"[{datetime.now()}] {bot.user} starting")
    fp = open(LOG_FILENAME, 'w')  # file pointer to log file
    event_db = r8gptDB.load_db(DB_FILENAME)
    scan_world_state.start()


bot.run(BOT_TOKEN)

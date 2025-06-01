import asyncio
import discord
from discord.ext import tasks
from discord import option
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta
import os
from r8gptInclude import (WORLDSAVE_PATH, DB_FILENAME, LOG_FILENAME, AI_ALERT_TIME, PLAYER_ALERT_TIME, REMINDER_TIME,
                          BOT_TOKEN, CH_LOG, CH_ALERT, CREWED_TAG, COMPLETED_TAG, AVAILABLE_TAG, LOCATION_DB)
import r8gptDB

DEBUG = True

# Necessary Bot intents
intents = discord.Intents.default()
intents.guilds = True
intents.messages = True
intents.message_content = True

SAVENAME = WORLDSAVE_PATH + '/Auto Save World.xml'
DIESEL_ENGINE = 'US_DieselEngine'
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
    def __init__(self, id_number, symbol, lead_num, train_type, num_units, engineer, latest_update_time,
                 route, track, dist):
        self.id_number = id_number      # Unique ID
        self.symbol = symbol            # Train tag symbol
        self.lead_num = lead_num        # Lead loco number
        self.train_type = train_type    # freight, passenger
        self.num_units = num_units      # Number of locos + cars total
        self.engineer = engineer        # AI, player, none
        self.latest_update_time = latest_update_time    # Last time this train was tracked
        self.route = route
        self.track = track
        self.dist = dist

    def __str__(self):
        return str(f'ID: {self.id_number}\nSymbol: {self.symbol}\nLead#: {self.lead_num}\nType: {self.train_type}\n'
                   f'Number of cars:{self.num_units}\nEngineer: {self.engineer}\nRoute: {self.route}\n'
                   f'Track: {self.track}\nDist: {self.dist}\nLast Update: {self.latest_update_time}')


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
            units.append(Car(file_name, unit_type, route_prefix, track_index, start_node, distance, reverse, load_weight,
                             dest_tag, unit_number, hazmat_tag))
        cuts.append(Cut(train_id, was_ai, direction, speed_limit, prev_signal, units.copy()))
        units.clear()
    return cuts


idleTrains = dict()
idleTrains2 = dict()
aiTrains = dict()
aiTrains2 = dict()
playerTrains = dict()
playerTrains2 = dict()
player_list = dict()
watched_trains = dict()
nbr_player_moving = 0
last_modified = 0
global fp
global last_world_datetime


def update_world_state(ai_trains, player_trains, idle_trains):
    tree = ET.parse(SAVENAME)
    root = tree.getroot()
    world_save_datetime = datetime.strptime(root.find('date').text.split('.')[0], '%Y-%m-%dT%H:%M:%S')
    trains = parse_train_loader(root)
    for train in trains:
        if train.consist[0].unit_type == DIESEL_ENGINE:  # We are only interested in consists with lead locos
            tid = train.train_id
            tag = train.consist[0].dest_tag
            nbr = train.consist[0].unit_number
            rp = train.consist[0].route
            ts = train.consist[0].track
            dist = train.consist[0].dist
            if 'amtrak' in train.consist[0].filename.lower():
                train_type = 'Passenger'
            else:
                train_type = 'Freight'
            if train.is_ai.lower() == 'true':
                ai_trains[tid] = Train(tid, tag, nbr, train_type, len(train.consist), 'AI',
                                       world_save_datetime, rp, ts, dist)
            elif tid in {value: key for key, value in player_list.items()}:
                player_id = [key for key, val in player_list.items() if val == tid]
                player_trains[tid] = Train(tid, tag, nbr, train_type, len(train.consist),
                                           player_id[0], world_save_datetime, rp, ts, dist)
            else:
                idle_trains[tid] = Train(tid, tag, nbr, train_type, len(train.consist),
                                         'None', world_save_datetime, rp, ts, dist)
        else:
            # First car is not a locomotive, so not a valid train
            pass
    return world_save_datetime


def find_player_train(train_tag):
    for train in idleTrains:
        if idleTrains[train].symbol == train_tag:
            return train
    return -1


def add_player_train(train_id, player_id, add_time):
    if train_id not in player_list:
        player_list[player_id] = train_id
        playerTrains[train_id] = idleTrains[train_id]
        playerTrains[train_id].engineer = player_id
        playerTrains[train_id].latest_update_time = add_time
        del idleTrains[train_id]


def del_player_train(train_id, player_id):
    if player_id in player_list and player_list[player_id] == train_id:
        del player_list[player_id]
        idleTrains[train_id] = playerTrains[train_id]
        idleTrains[train_id].engineer = 'None'
        del playerTrains[train_id]


def log_msg(msg):
    global fp

    fp = open(LOG_FILENAME,'a')
    fp.write(msg + '\n')
    fp.close()


bot = discord.Bot(intents=intents)


@bot.slash_command(name='test', description="test a command")
async def test(ctx: discord.ApplicationContext):
    thread = ctx.channel
    await thread.send("tested")


@bot.slash_command(name='crew', description=f"Crew a train")
@option("symbol", description="Train symbol", required=True)
# NOTE: This command must be executed within a forum thread
async def crew(ctx: discord.ApplicationContext, symbol: str):
    global last_world_datetime

    thread = ctx.channel
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
        ret = find_player_train(symbol)
        if ret != -1:
            add_player_train(ret, ctx.author.mention, last_world_datetime)
            if tag_to_add not in current_tags:
                current_tags.append(tag_to_add)
            if tag_to_remove in current_tags:
                current_tags.remove(tag_to_remove)
            msg = f'[{playerTrains[ret].latest_update_time}] {ctx.author.display_name} crewed {symbol}'
            await thread.edit(applied_tags=current_tags)
            log_msg(msg)
            r8gptDB.add_event(playerTrains[ret].latest_update_time, ctx.author.display_name,
                              'CREW', symbol, event_db)
            r8gptDB.save_db(DB_FILENAME, event_db)
            await thread.send(msg)
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
        for train in playerTrains:
            if playerTrains[train].engineer == ctx.author.mention:
                del_player_train(train, ctx.author.mention)
                if tag_to_add not in current_tags:
                    current_tags.append(tag_to_add)
                if tag_to_remove in current_tags:
                    current_tags.remove(tag_to_remove)
                msg = (f'[{idleTrains[train].latest_update_time}] {ctx.author.display_name} tied down train '
                       f'{idleTrains[train].symbol} at {location}')
                await thread.send(msg)
                await thread.edit(applied_tags=current_tags)
                log_msg(msg)
                r8gptDB.add_event(idleTrains[train].latest_update_time, ctx.author.display_name,
                                  'TIED_DOWN', idleTrains[train].symbol, event_db)
                r8gptDB.save_db(DB_FILENAME, event_db)
                return
        else:
            await ctx.respond(f'Unable to tie down; are you sure you are crewing this job?', ephemeral=True)

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
        await ctx.respond(f'Attempting to mark as completed: {symbol}', ephemeral=True)
        for train in playerTrains:
            if playerTrains[train].engineer == ctx.author.mention:
                del_player_train(train, ctx.author.mention)
                if tag_to_add not in current_tags:
                    current_tags.append(tag_to_add)
                if tag1_to_remove in current_tags:
                    current_tags.remove(tag1_to_remove)
                if tag2_to_remove in current_tags:
                    current_tags.remove(tag2_to_remove)
                msg = (f'[{idleTrains[train].latest_update_time}] {ctx.author.display_name} marked train '
                       f'{idleTrains[train].symbol} {COMPLETED_TAG}')
                if len(notes) > 0:
                    msg += f'. Notes: {notes}'
                await thread.send(msg)
                await thread.edit(applied_tags=current_tags)
                log_msg(msg)
                r8gptDB.add_event(idleTrains[train].latest_update_time, ctx.author.display_name,
                                  'MARKED_COMPLETE', idleTrains[train].symbol, event_db)
                r8gptDB.save_db(DB_FILENAME, event_db)
                return
        else:
            await ctx.respond(f'Unable to mark as complete; are you sure you are clocked in?', ephemeral=True)
    except discord.Forbidden:
        await ctx.respond('[r8GPT] **ERROR**: I do not have permission to edit this thread.', ephemeral=True)
    except Exception as e:
        await ctx.respond(f'[r8GPT] **ERROR**: {e}', ephemeral=True)


@bot.slash_command(name="list_ai", description="List current AI trains")
async def list_ai(ctx: discord.ApplicationContext):
    msg = ''
    for train in aiTrains:
        msg += f'[{aiTrains[train].symbol}], Lead# {aiTrains[train].lead_num}, Units: {aiTrains[train].num_units}\n'
    await ctx.respond(msg, ephemeral=True)


@bot.slash_command(name='list_stuck', description="List current stuck trains")
async def list_stuck(ctx: discord.ApplicationContext):
    msg = ''
    for train in watched_trains:
        if train in aiTrains:
            msg += (f'[{aiTrains[train].symbol}], Lead# {aiTrains[train].lead_num}, '
                    f'Units: {aiTrains[train].num_units}\n')
        elif train in playerTrains:
            msg += (f'[{playerTrains[train].symbol}], Lead# {playerTrains[train].lead_num}, '
                    f'Units: {playerTrains[train].num_units}\n')
        else:
            return

    await ctx.respond(msg, ephemeral=True)


@bot.slash_command(name='list_player', description="List current AI trains")
async def list_player(ctx: discord.ApplicationContext):
    msg = ''
    for train in playerTrains:
        msg += (f'{playerTrains[train].engineer} : [{playerTrains[train].symbol}]# {playerTrains[train].lead_num}, '
                f'total cars: {playerTrains[train].num_units}\n')
    if len(msg) < 1:
        msg = 'No player trains being tracked at present.'
    await ctx.respond(msg, ephemeral=True)


@tasks.loop(seconds=90)
async def scan_world_state():
    global last_modified
    global fp
    global last_world_datetime

    async def send_ch_msg(ch_name, ch_msg):
        """
        Send messages to discord channel
        :param ch_name: name of discord channel to write message to
        :param ch_msg: Message content
        :return: 0 if successful, -1 if error
        """
        if ch_msg.lower() == 'none':
            return 0

        for guild in bot.guilds:
            for channel in guild.text_channels + guild.forum_channels:
                threads = channel.threads
                for thread in threads:
                    if thread.name.lower() == ch_name.lower():
                        # write to matching thread name
                        await thread.send('[r8GPT] ' + ch_msg)
                        log_msg(msg)
                        return 0

                if channel.name.lower() == ch_name.lower():
                    # Write to a matching channel name
                    await channel.send('[r8GPT] ' + ch_msg)
                    log_msg(msg)
                    return 0
        print(f"[Warning] thread / channel {ch_name} not found.")
        return -1

    if len(idleTrains) == 0:    # No idle trains means we need to read initial state
        last_modified = os.stat(SAVENAME).st_mtime
        last_world_datetime = update_world_state(aiTrains, playerTrains, idleTrains)
        msg = (f'{last_world_datetime} Initializing: '
               f'AI trains found: {len(aiTrains)}, '
               f'Idle trains found: {len(idleTrains)}')
        await send_ch_msg(CH_LOG, msg)
        
    if os.stat(SAVENAME).st_mtime != last_modified:     # Has file timestamp changed since last iteration?
        last_modified = os.stat(SAVENAME).st_mtime
        last_world_datetime = update_world_state(aiTrains2, playerTrains2, idleTrains2)

        # Check to see if any trains have been deleted
        nbr_ai_removed = 0
        nbr_player_removed = 0
        ai_trains_removed = list()
        player_trains_removed = list()
        for trainID in aiTrains:
            if trainID not in aiTrains2:
                ai_trains_removed.append(trainID)
        for trainID in playerTrains:        # Currently this will never be true as the player_train functions mess with the playerTrains structure
            if trainID not in playerTrains2:
                player_trains_removed.append(trainID)

        for tid in ai_trains_removed:
            nbr_ai_removed += 1
            msg = f'{last_world_datetime} Train removed: [AI] {aiTrains[tid].symbol} ({tid})'
            await send_ch_msg(CH_LOG, msg)
            print(msg)
            if tid in watched_trains:
                del watched_trains[tid]  # No longer need to watch
            del aiTrains[tid]

        for tid in player_trains_removed:
            nbr_player_removed += 1
            msg = f'{last_world_datetime} Train removed: [{playerTrains[tid].engineer}] {playerTrains[tid].symbol} ({tid})'
            await send_ch_msg(CH_LOG, msg)
            print(msg)
            if tid in watched_trains:
                del watched_trains[tid]  # No longer need to watch
            del playerTrains[tid]

        nbr_ai_moving = 0
        nbr_player_moving = 0
        nbr_ai_stopped = 0
        nbr_ai_added = 0
        nbr_player_stopped = 0
        nbr_player_added = 0

        # check AI train status
        for trainID in aiTrains2:
            if trainID in aiTrains:
                if aiTrains2[trainID].symbol != aiTrains[trainID].symbol:
                    print(f'{last_world_datetime} Train re-tagged: {trainID} has changed tags since last update '
                          f'({aiTrains[trainID].symbol} -> {aiTrains2[trainID].symbol}); Updating record.')
                    aiTrains[trainID] = aiTrains2[trainID]
                elif aiTrains2[trainID].route != aiTrains[trainID].route \
                        or aiTrains2[trainID].track != aiTrains[trainID].track \
                        or aiTrains2[trainID].dist != aiTrains[trainID].dist:
                    # AI train HAS MOVED since last update
                    nbr_ai_moving += 1
                    if trainID in watched_trains:
                        if DEBUG:
                            print(f'Watched train: {aiTrains[trainID].symbol} is now on the move. Removing watch')
                        del watched_trains[trainID]     # No longer need to watch
                    aiTrains[trainID].latest_update_time = aiTrains2[trainID].latest_update_time
                elif aiTrains2[trainID].route == aiTrains[trainID].route \
                        and aiTrains2[trainID].track == aiTrains[trainID].track \
                        and aiTrains2[trainID].dist == aiTrains[trainID].dist:
                    # AI train HAS NOT MOVED since last update
                    nbr_ai_stopped += 1
                    td = aiTrains2[trainID].latest_update_time - aiTrains[trainID].latest_update_time
                    sub = LOCATION_DB[int(aiTrains2[trainID].route[0])]
                    msg = ''
                    if td > timedelta(minutes=AI_ALERT_TIME):
                        if trainID not in watched_trains:
                            watched_trains[trainID] = [aiTrains[trainID].latest_update_time, 1]
                            msg = f'{last_world_datetime} **POSSIBLE STUCK TRAIN**: '
                            msg += (f'[AI] {aiTrains2[trainID].symbol} ({trainID})'
                                    f' has not moved for {td}, Location: {sub} / '
                                    f'{aiTrains2[trainID].track}')
                            await send_ch_msg(CH_ALERT, msg)
                        elif ((aiTrains2[trainID].latest_update_time - watched_trains[trainID][0])
                              // watched_trains[trainID][1] > timedelta(minutes=REMINDER_TIME)):
                            watched_trains[trainID][1] += 1
                            msg = f'{last_world_datetime} **STUCK TRAIN REMINDER # {watched_trains[trainID][1]}**: '
                            msg += (f'[AI] {aiTrains2[trainID].symbol} ({trainID})'
                                    f' has not moved for {td}, Location: {sub} / '
                                    f'{aiTrains2[trainID].track}')
                            await send_ch_msg(CH_ALERT, msg)
                        else:
                            pass    # We have already notified at least once, now backing off before another notice
                    print(f'[AI] {aiTrains2[trainID].symbol} ({trainID}) has not moved for {td}, '
                          f'Location: {sub} / {aiTrains[trainID].track}')
                else:
                    print(f'something odd in comparing these two:\n{aiTrains[trainID]}\n{aiTrains2[trainID]}')
            else:
                nbr_ai_added += 1
                msg = f'{last_world_datetime} Train spawned: {aiTrains2[trainID].symbol} ({trainID})'
                aiTrains[trainID] = aiTrains2[trainID]
                print(msg)
                await send_ch_msg(CH_LOG, msg)
        # Check player train status
        for trainID in playerTrains2:
            if trainID in playerTrains:
                if playerTrains2[trainID].symbol != playerTrains[trainID].symbol:
                    print(f'{last_world_datetime} Player train re-tagged: {trainID} has changed tags since last update '
                          f'({playerTrains[trainID].symbol} -> {playerTrains2[trainID].symbol}); Updating record.')
                    playerTrains[trainID] = playerTrains2[trainID]

                elif playerTrains2[trainID].route != playerTrains[trainID].route \
                        or playerTrains2[trainID].track != playerTrains[trainID].track \
                        or playerTrains2[trainID].dist != playerTrains[trainID].dist:
                    # player train HAS MOVED since last update
                    if trainID in watched_trains:
                        if DEBUG:
                            print(f'Watched train: {playerTrains[trainID].symbol} is now on the move. Removing watch')
                        del watched_trains[trainID]     # No longer need to watch
                    nbr_player_moving += 1
                    playerTrains[trainID].latest_update_time = playerTrains2[trainID].latest_update_time

                elif playerTrains2[trainID].route == playerTrains[trainID].route \
                        and playerTrains2[trainID].track == playerTrains[trainID].track \
                        and playerTrains2[trainID].dist == playerTrains[trainID].dist:
                    # Player train HAS NOT MOVED since last update
                    nbr_player_stopped += 1
                    td = playerTrains2[trainID].latest_update_time - playerTrains[trainID].latest_update_time
                    sub = LOCATION_DB[int(playerTrains2[trainID].route[0])]
                    if td > timedelta(minutes=PLAYER_ALERT_TIME):
                        if trainID not in watched_trains:
                            watched_trains[trainID] = [playerTrains[trainID].latest_update_time, 2]
                            msg = f'{last_world_datetime} **POSSIBLE STUCK TRAIN**: '
                            msg += (f'[{playerTrains2[trainID].engineer}] {playerTrains2[trainID].symbol} ({trainID})'
                                    f' has not moved for {td}, Location: {sub} / '
                                    f'{playerTrains2[trainID].track}')
                            await send_ch_msg(CH_ALERT, msg)
                        elif ((playerTrains2[trainID].latest_update_time - watched_trains[trainID][0])
                              // watched_trains[trainID][1] > timedelta(minutes=REMINDER_TIME)):
                            watched_trains[trainID][1] += 1
                            msg = f'{last_world_datetime} **STUCK TRAIN REMINDER # {watched_trains[trainID][1]}**: '
                            msg += (f'[{playerTrains2[trainID].engineer}] {playerTrains2[trainID].symbol} ({trainID})'
                                    f' has not moved for {td}, Location: {sub} / '
                                    f'{playerTrains2[trainID].track}')
                            await send_ch_msg(CH_ALERT, msg)
                        else:
                            pass    # We have already notified at least once, now backing off before another notice
                    print(f'[Player: {playerTrains2[trainID].engineer}] {playerTrains2[trainID].symbol} ({trainID}) '
                          f'has not moved for {td}'
                          f' Location: {sub} / {playerTrains[trainID].track}')
                else:
                    print(f'something odd in comparing these two:\n{playerTrains[trainID]}\n{playerTrains2[trainID]}')
            else:
                nbr_player_added += 1
                print(f'Train added: {playerTrains2[trainID][1]} ({trainID})')
                playerTrains[trainID] = playerTrains2[trainID]

        msg = (f'{last_world_datetime} Summary: AI ({nbr_ai_moving}M, {nbr_ai_stopped}S, +{nbr_ai_added}, '
               f'-{nbr_ai_removed}) | Player ({nbr_player_moving}M, {nbr_player_stopped}S) | Idle ({len(idleTrains)})')
        await send_ch_msg(CH_LOG, msg)
        print(msg)
        aiTrains2.clear()
        playerTrains2.clear()


@bot.event
async def on_ready():
    global fp
    global event_db

    print(f"[{datetime.now()}] {bot.user} starting")
    fp = open(LOG_FILENAME, 'w')     # file pointer to log file
    event_db = r8gptDB.load_db(DB_FILENAME)
    scan_world_state.start()

bot.run(BOT_TOKEN)


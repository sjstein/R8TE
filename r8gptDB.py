import csv

timestamp = 'timestamp'
discord_name = 'discord_name'
event = 'event_name'
train_id = 'train_id'

db_field_list = [discord_name, event, timestamp, train_id]


def load_db(filename: str) -> list:
    ldb = list()
    try:
        with open(filename, newline='') as csvfile:
            input_file = csv.DictReader(csvfile)
            for row in input_file:
                ldb.append(row)
        return ldb

    except FileNotFoundError as e:
        print(f'\nr8gpt: Database file {filename} not found, creating a new one')
        with open(filename, 'w', newline='') as csvfile:
            csvwriter = csv.DictWriter(csvfile, fieldnames=db_field_list)
            csvwriter.writeheader()
        return load_db(filename)

    except Exception as e:
        print(f'\nr8gpt ({__name__}.py: FATAL exception in load_db, type unknown - contact devs')
        exit(-1)


def save_db(filename: str, ldb: list) -> int:
    try:
        with open(filename, 'w', newline='') as csvfile:
            csvwriter = csv.DictWriter(csvfile, fieldnames=db_field_list)
            csvwriter.writeheader()
            for row in ldb:
                csvwriter.writerow(row)
        return len(ldb)

    except Exception as e:
        print(f'\nr8dium ({__name__}.py: FATAL exception in save_db, type unknown - contact devs')
        exit(-1)


def add_event(ts, user_name, evt, tid, ldb: list):
    record = {timestamp: ts, discord_name: user_name, event: evt, train_id: tid}
    ldb.append(record)

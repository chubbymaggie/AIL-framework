#!/usr/bin/env python3
# -*-coding:UTF-8 -*

import os
import sys
import gzip
import io
import redis
import base64
import datetime
import time

from sflock.main import unpack
import sflock

from Helper import Process
from pubsublogger import publisher

sys.path.append(os.path.join(os.environ['AIL_BIN'], 'packages/'))
import Tag

sys.path.append(os.path.join(os.environ['AIL_BIN'], 'lib/'))
import ConfigLoader

def create_paste(uuid, paste_content, ltags, ltagsgalaxies, name):

    now = datetime.datetime.now()
    save_path = 'submitted/' + now.strftime("%Y") + '/' + now.strftime("%m") + '/' + now.strftime("%d") + '/' + name + '.gz'

    full_path = filename = os.path.join(os.environ['AIL_HOME'],
                            p.config.get("Directories", "pastes"), save_path)

    if os.path.isfile(full_path):
        addError(uuid, 'File: ' + save_path + ' already exist in submitted pastes')
        return 1

    try:
        gzipencoded = gzip.compress(paste_content)
        gzip64encoded = base64.standard_b64encode(gzipencoded).decode()
    except:
        abord_file_submission(uuid, "file error")
        return 1

    # use relative path
    rel_item_path = save_path.replace(PASTES_FOLDER, '', 1)

    # send paste to Global module
    relay_message = "{0} {1}".format(rel_item_path, gzip64encoded)
    p.populate_set_out(relay_message, 'Mixer')

    # increase nb of paste by feeder name
    r_serv_log_submit.hincrby("mixer_cache:list_feeder", "submitted", 1)

    # add tags
    for tag in ltags:
        Tag.add_tag('item', tag, rel_item_path)

    for tag in ltagsgalaxies:
        Tag.add_tag('item', tag, rel_item_path)

    r_serv_log_submit.incr(uuid + ':nb_end')
    r_serv_log_submit.incr(uuid + ':nb_sucess')

    if r_serv_log_submit.get(uuid + ':nb_end') == r_serv_log_submit.get(uuid + ':nb_total'):
        r_serv_log_submit.set(uuid + ':end', 1)

    print('    {} send to Global'.format(rel_item_path))
    r_serv_log_submit.sadd(uuid + ':paste_submit_link', rel_item_path)

    curr_date = datetime.date.today()
    serv_statistics.hincrby(curr_date.strftime("%Y%m%d"),'submit_paste', 1)

    return 0

def addError(uuid, errorMessage):
    print(errorMessage)
    error = r_serv_log_submit.get(uuid + ':error')
    if error != None:
        r_serv_log_submit.set(uuid + ':error', error + '<br></br>' + errorMessage)
    r_serv_log_submit.incr(uuid + ':nb_end')

def abord_file_submission(uuid, errorMessage):
    addError(uuid, errorMessage)
    r_serv_log_submit.set(uuid + ':end', 1)
    curr_date = datetime.date.today()
    serv_statistics.hincrby(curr_date.strftime("%Y%m%d"),'submit_abord', 1)
    remove_submit_uuid(uuid)


def remove_submit_uuid(uuid):
    # save temp value on disk
    r_serv_db.delete(uuid + ':ltags')
    r_serv_db.delete(uuid + ':ltagsgalaxies')
    r_serv_db.delete(uuid + ':paste_content')
    r_serv_db.delete(uuid + ':isfile')
    r_serv_db.delete(uuid + ':password')

    r_serv_log_submit.expire(uuid + ':end', expire_time)
    r_serv_log_submit.expire(uuid + ':processing', expire_time)
    r_serv_log_submit.expire(uuid + ':nb_total', expire_time)
    r_serv_log_submit.expire(uuid + ':nb_sucess', expire_time)
    r_serv_log_submit.expire(uuid + ':nb_end', expire_time)
    r_serv_log_submit.expire(uuid + ':error', expire_time)
    r_serv_log_submit.expire(uuid + ':paste_submit_link', expire_time)

    # delete uuid
    r_serv_db.srem('submitted:uuid', uuid)
    print('{} all file submitted'.format(uuid))

def get_item_date(item_filename):
    l_directory = item_filename.split('/')
    return '{}{}{}'.format(l_directory[-4], l_directory[-3], l_directory[-2])

def verify_extention_filename(filename):
    if not '.' in filename:
        return True
    else:
        file_type = filename.rsplit('.', 1)[1]

        #txt file
        if file_type in ALLOWED_EXTENSIONS:
            return True
        else:
            return False

if __name__ == "__main__":

    publisher.port = 6380
    publisher.channel = "Script"

    config_loader = ConfigLoader.ConfigLoader()

    r_serv_db = config_loader.get_redis_conn("ARDB_DB")
    r_serv_log_submit = config_loader.get_redis_conn("Redis_Log_submit")
    r_serv_tags = config_loader.get_redis_conn("ARDB_Tags")
    r_serv_metadata = config_loader.get_redis_conn("ARDB_Metadata")
    serv_statistics = config_loader.get_redis_conn("ARDB_Statistics")

    expire_time = 120
    MAX_FILE_SIZE = 1000000000
    ALLOWED_EXTENSIONS = ['txt', 'sh', 'pdf']

    config_section = 'submit_paste'
    p = Process(config_section)

    PASTES_FOLDER = os.path.join(os.environ['AIL_HOME'], config_loader.get_config_str("Directories", "pastes")) + '/'

    config_loader = None

    while True:

        # paste submitted
        if r_serv_db.scard('submitted:uuid') > 0:
            uuid = r_serv_db.srandmember('submitted:uuid')

            # get temp value save on disk
            ltags = r_serv_db.smembers(uuid + ':ltags')
            ltagsgalaxies = r_serv_db.smembers(uuid + ':ltagsgalaxies')
            paste_content = r_serv_db.get(uuid + ':paste_content')
            isfile = r_serv_db.get(uuid + ':isfile')
            password = r_serv_db.get(uuid + ':password')

            # needed if redis is restarted
            r_serv_log_submit.set(uuid + ':end', 0)
            r_serv_log_submit.set(uuid + ':processing', 0)
            r_serv_log_submit.set(uuid + ':nb_total', -1)
            r_serv_log_submit.set(uuid + ':nb_end', 0)
            r_serv_log_submit.set(uuid + ':nb_sucess', 0)


            r_serv_log_submit.set(uuid + ':processing', 1)

            if isfile == 'True':
                file_full_path = paste_content

                if not os.path.exists(file_full_path):
                    abord_file_submission(uuid, "Server Error, the archive can't be found")
                    continue

                #verify file lengh
                if os.stat(file_full_path).st_size > MAX_FILE_SIZE:
                    abord_file_submission(uuid, 'File :{} too large'.format(file_full_path))

                else:
                    filename = file_full_path.split('/')[-1]
                    if not '.' in filename:
                        # read file
                        try:
                            with open(file_full_path,'r') as f:
                                content = f.read()
                        except:
                            abord_file_submission(uuid, "file error")
                            continue
                        r_serv_log_submit.set(uuid + ':nb_total', 1)
                        create_paste(uuid, content.encode(), ltags, ltagsgalaxies, uuid)
                        remove_submit_uuid(uuid)

                    else:
                        file_type = filename.rsplit('.', 1)[1]

                        #txt file
                        if file_type in ALLOWED_EXTENSIONS:
                            with open(file_full_path,'r') as f:
                                content = f.read()
                            r_serv_log_submit.set(uuid + ':nb_total', 1)
                            create_paste(uuid, content.encode(), ltags, ltagsgalaxies, uuid)
                            remove_submit_uuid(uuid)
                        #compressed file
                        else:
                            #decompress file
                            try:
                                if password == None:
                                    files = unpack(file_full_path.encode())
                                    #print(files.children)
                                else:
                                    try:
                                        files = unpack(file_full_path.encode(), password=password.encode())
                                        #print(files.children)
                                    except sflock.exception.IncorrectUsageException:
                                        abord_file_submission(uuid, "Wrong Password")
                                        continue
                                    except:
                                        abord_file_submission(uuid, "file decompression error")
                                        continue
                                print('unpacking {} file'.format(files.unpacker))
                                if(not files.children):
                                    abord_file_submission(uuid, "Empty compressed file")
                                    continue
                                # set number of files to submit
                                r_serv_log_submit.set(uuid + ':nb_total', len(files.children))
                                n = 1
                                for child in files.children:
                                    if verify_extention_filename(child.filename.decode()):
                                        create_paste(uuid, child.contents, ltags, ltagsgalaxies, uuid+'_'+ str(n) )
                                        n = n + 1
                                    else:
                                        print('bad extention')
                                        addError(uuid, 'Bad file extension: {}'.format(child.filename.decode()) )

                            except FileNotFoundError:
                                print('file not found')
                                addError(uuid, 'File not found: {}'.format(file_full_path), uuid )

                            remove_submit_uuid(uuid)



            # textarea input paste
            else:
                r_serv_log_submit.set(uuid + ':nb_total', 1)
                create_paste(uuid, paste_content.encode(), ltags, ltagsgalaxies, uuid)
                remove_submit_uuid(uuid)
                time.sleep(0.5)

        # wait for paste
        else:
            publisher.debug("Script submit_paste is Idling 10s")
            time.sleep(3)

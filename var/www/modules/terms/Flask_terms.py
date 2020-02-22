#!/usr/bin/env python3
# -*-coding:UTF-8 -*

'''
    Flask functions and routes for the trending modules page

    note: The matching of credential against supplied credential is done using Levenshtein distance
'''
import json
import redis
import datetime
import calendar
import flask
from flask import Flask, render_template, jsonify, request, Blueprint, url_for, redirect, Response

from Role_Manager import login_admin, login_analyst, login_user_no_api, login_read_only
from flask_login import login_required, current_user

import re
from pprint import pprint
import Levenshtein

# ---------------------------------------------------------------

import Paste
import Term

# ============ VARIABLES ============
import Flask_config

app = Flask_config.app
baseUrl = Flask_config.baseUrl
r_serv_term = Flask_config.r_serv_term
r_serv_cred = Flask_config.r_serv_cred
r_serv_db = Flask_config.r_serv_db
bootstrap_label = Flask_config.bootstrap_label

terms = Blueprint('terms', __name__, template_folder='templates')

'''TERM'''
DEFAULT_MATCH_PERCENT = 50

#tracked
TrackedTermsSet_Name = "TrackedSetTermSet"
TrackedTermsDate_Name = "TrackedTermDate"
#black
BlackListTermsDate_Name = "BlackListTermDate"
BlackListTermsSet_Name = "BlackListSetTermSet"
#regex
TrackedRegexSet_Name = "TrackedRegexSet"
TrackedRegexDate_Name = "TrackedRegexDate"
#set
TrackedSetSet_Name = "TrackedSetSet"
TrackedSetDate_Name = "TrackedSetDate"

# notifications enabled/disabled
# same value as in `bin/NotificationHelper.py`
TrackedTermsNotificationEnabled_Name = "TrackedNotifications"

# associated notification email addresses for a specific term`
# same value as in `bin/NotificationHelper.py`
# Keys will be e.g. TrackedNotificationEmails_<TERMNAME>
TrackedTermsNotificationEmailsPrefix_Name = "TrackedNotificationEmails_"
TrackedTermsNotificationTagsPrefix_Name = "TrackedNotificationTags_"

'''CRED'''
REGEX_CRED = '[a-z]+|[A-Z]{3,}|[A-Z]{1,2}[a-z]+|[0-9]+'
REDIS_KEY_NUM_USERNAME = 'uniqNumForUsername'
REDIS_KEY_NUM_PATH = 'uniqNumForUsername'
REDIS_KEY_ALL_CRED_SET = 'AllCredentials'
REDIS_KEY_ALL_CRED_SET_REV = 'AllCredentialsRev'
REDIS_KEY_ALL_PATH_SET = 'AllPath'
REDIS_KEY_ALL_PATH_SET_REV = 'AllPathRev'
REDIS_KEY_MAP_CRED_TO_PATH = 'CredToPathMapping'



# ============ FUNCTIONS ============

def Term_getValueOverRange(word, startDate, num_day, per_paste=""):
    passed_days = 0
    oneDay = 60*60*24
    to_return = []
    curr_to_return = 0
    for timestamp in range(startDate, startDate - max(num_day)*oneDay, -oneDay):
        value = r_serv_term.hget(per_paste+str(timestamp), word)
        curr_to_return += int(value) if value is not None else 0
        for i in num_day:
            if passed_days == i-1:
                to_return.append(curr_to_return)
        passed_days += 1
    return to_return

#Mix suplied username, if extensive is set, slice username(s) with different windows
def mixUserName(supplied, extensive=False):
    #e.g.: John Smith
    terms = supplied.split()[:2]
    usernames = []
    if len(terms) == 1:
        terms.append(' ')

    #john, smith, John, Smith, JOHN, SMITH
    usernames += [terms[0].lower()]
    usernames += [terms[1].lower()]
    usernames += [terms[0][0].upper() + terms[0][1:].lower()]
    usernames += [terms[1][0].upper() + terms[1][1:].lower()]
    usernames += [terms[0].upper()]
    usernames += [terms[1].upper()]

    #johnsmith, smithjohn, JOHNsmith, johnSMITH, SMITHjohn, smithJOHN
    usernames += [(terms[0].lower() + terms[1].lower()).strip()]
    usernames += [(terms[1].lower() + terms[0].lower()).strip()]
    usernames += [(terms[0].upper() + terms[1].lower()).strip()]
    usernames += [(terms[0].lower() + terms[1].upper()).strip()]
    usernames += [(terms[1].upper() + terms[0].lower()).strip()]
    usernames += [(terms[1].lower() + terms[0].upper()).strip()]
    #Jsmith, JSmith, jsmith, jSmith, johnS, Js, JohnSmith, Johnsmith, johnSmith
    usernames += [(terms[0][0].upper() + terms[1][0].lower() + terms[1][1:].lower()).strip()]
    usernames += [(terms[0][0].upper() + terms[1][0].upper() + terms[1][1:].lower()).strip()]
    usernames += [(terms[0][0].lower() + terms[1][0].lower() + terms[1][1:].lower()).strip()]
    usernames += [(terms[0][0].lower() + terms[1][0].upper() + terms[1][1:].lower()).strip()]
    usernames += [(terms[0].lower() + terms[1][0].upper()).strip()]
    usernames += [(terms[0].upper() + terms[1][0].lower()).strip()]
    usernames += [(terms[0][0].upper() + terms[0][1:].lower() + terms[1][0].upper() + terms[1][1:].lower()).strip()]
    usernames += [(terms[0][0].upper() + terms[0][1:].lower() + terms[1][0].lower() + terms[1][1:].lower()).strip()]
    usernames += [(terms[0][0].lower() + terms[0][1:].lower() + terms[1][0].upper() + terms[1][1:].lower()).strip()]

    if not extensive:
        return usernames

    #Slice the supplied username(s)
    mixedSupplied = supplied.replace(' ','')
    minWindow = 3 if len(mixedSupplied)/2 < 4 else len(mixedSupplied)/2
    for winSize in range(3,len(mixedSupplied)):
        for startIndex in range(0, len(mixedSupplied)-winSize):
            usernames += [mixedSupplied[startIndex:startIndex+winSize]]

    filtered_usernames = []
    for usr in usernames:
        if len(usr) > 2:
            filtered_usernames.append(usr)
    return filtered_usernames

def save_tag_to_auto_push(list_tag):
    for tag in set(list_tag):
        #limit tag length
        if len(tag) > 49:
            tag = tag[0:48]
        r_serv_db.sadd('list_export_tags', tag)

# ============ ROUTES ============

 # TODO: remove + clean

# @terms.route("/terms_plot_tool/")
# @login_required
# @login_read_only
# def terms_plot_tool():
#     term =  request.args.get('term')
#     if term is not None:
#         return render_template("terms_plot_tool.html", term=term)
#     else:
#         return render_template("terms_plot_tool.html", term="")
#
#
# @terms.route("/terms_plot_tool_data/")
# @login_required
# @login_read_only
# def terms_plot_tool_data():
#     oneDay = 60*60*24
#     range_start =  datetime.datetime.utcfromtimestamp(int(float(request.args.get('range_start')))) if request.args.get('range_start') is not None else 0;
#     range_start = range_start.replace(hour=0, minute=0, second=0, microsecond=0)
#     range_start = calendar.timegm(range_start.timetuple())
#     range_end =  datetime.datetime.utcfromtimestamp(int(float(request.args.get('range_end')))) if request.args.get('range_end') is not None else 0;
#     range_end = range_end.replace(hour=0, minute=0, second=0, microsecond=0)
#     range_end = calendar.timegm(range_end.timetuple())
#     term =  request.args.get('term')
#
#     per_paste = request.args.get('per_paste')
#     if per_paste == "1" or per_paste is None:
#         per_paste = "per_paste_"
#     else:
#         per_paste = ""
#
#     if term is None:
#         return "None"
#
#     else:
#         value_range = []
#         for timestamp in range(range_start, range_end+oneDay, oneDay):
#             value = r_serv_term.hget(per_paste+str(timestamp), term)
#             curr_value_range = int(value) if value is not None else 0
#             value_range.append([timestamp, curr_value_range])
#         value_range.insert(0,term)
#         return jsonify(value_range)
#

# @terms.route("/terms_plot_top/"
# @login_required
# @login_read_only
# def terms_plot_top():
#     per_paste = request.args.get('per_paste')
#     per_paste = per_paste if per_paste is not None else 1
#     return render_template("terms_plot_top.html", per_paste=per_paste)
# 
#
# @terms.route("/terms_plot_top_data/")
# @login_required
# @login_read_only
# def terms_plot_top_data():
#     oneDay = 60*60*24
#     today = datetime.datetime.now()
#     today = today.replace(hour=0, minute=0, second=0, microsecond=0)
#     today_timestamp = calendar.timegm(today.timetuple())
#
#     per_paste = request.args.get('per_paste')
#     if per_paste == "1" or per_paste is None:
#         per_paste = "per_paste_"
#     else:
#         per_paste = ""
#
#     set_day = per_paste + "TopTermFreq_set_day_" + str(today_timestamp)
#     set_week = per_paste + "TopTermFreq_set_week";
#     set_month = per_paste + "TopTermFreq_set_month";
#
#     the_set = per_paste + request.args.get('set')
#     num_day = int(request.args.get('num_day'))
#
#     if the_set is None:
#         return "None"
#     else:
#         to_return = []
#         if "TopTermFreq_set_day" in the_set:
#             the_set += "_" + str(today_timestamp)
#
#         for term, tot_value in r_serv_term.zrevrangebyscore(the_set, '+inf', '-inf', withscores=True, start=0, num=20):
#             position = {}
#             position['day'] = r_serv_term.zrevrank(set_day, term)
#             position['day'] = position['day']+1 if position['day'] is not None else "<20"
#             position['week'] = r_serv_term.zrevrank(set_week, term)
#             position['week'] = position['week']+1 if position['week'] is not None else "<20"
#             position['month'] = r_serv_term.zrevrank(set_month, term)
#             position['month'] = position['month']+1 if position['month'] is not None else "<20"
#             value_range = []
#             for timestamp in range(today_timestamp, today_timestamp - num_day*oneDay, -oneDay):
#                 value = r_serv_term.hget(per_paste+str(timestamp), term)
#                 curr_value_range = int(value) if value is not None else 0
#                 value_range.append([timestamp, curr_value_range])
#
#             to_return.append([term, value_range, tot_value, position])
#
#         return jsonify(to_return)


@terms.route("/credentials_tracker/")
@login_required
@login_read_only
def credentials_tracker():
    return render_template("credentials_tracker.html")

@terms.route("/credentials_management_query_paste/", methods=['GET', 'POST'])
@login_required
@login_user_no_api
def credentials_management_query_paste():
    cred =  request.args.get('cred')
    allPath = request.json['allPath']

    paste_info = []
    for pathNum in allPath:
        path = r_serv_cred.hget(REDIS_KEY_ALL_PATH_SET_REV, pathNum)
        paste = Paste.Paste(path)
        p_date = str(paste._get_p_date())
        p_date = p_date[0:4]+'/'+p_date[4:6]+'/'+p_date[6:8]
        p_source = paste.p_source
        p_encoding = paste._get_p_encoding()
        p_size = paste.p_size
        p_mime = paste.p_mime
        p_lineinfo = paste.get_lines_info()
        p_content = paste.get_p_content()
        if p_content != 0:
            p_content = p_content[0:400]
        paste_info.append({"path": path, "date": p_date, "source": p_source, "encoding": p_encoding, "size": p_size, "mime": p_mime, "lineinfo": p_lineinfo, "content": p_content})

    return jsonify(paste_info)

@terms.route("/credentials_management_action/", methods=['GET'])
@login_required
@login_user_no_api
def cred_management_action():

    supplied =  request.args.get('term')
    action = request.args.get('action')
    section = request.args.get('section')
    extensive = request.args.get('extensive')
    extensive = True if extensive == "true" else False

    if extensive:
        #collectDico
        AllUsernameInRedis = r_serv_cred.hgetall(REDIS_KEY_ALL_CRED_SET).keys()
    uniq_num_set = set()
    if action == "seek":
        possibilities = mixUserName(supplied, extensive)
        for poss in possibilities:
            num = r_serv_cred.hget(REDIS_KEY_ALL_CRED_SET, poss)
            if num is not None:
                uniq_num_set.add(num)
            for num in r_serv_cred.smembers(poss):
                uniq_num_set.add(num)
        #Extensive /!\
        if extensive:
            iter_num = 0
            tot_iter = len(AllUsernameInRedis)*len(possibilities)
            for tempUsername in AllUsernameInRedis:
                for poss in possibilities:
                    #FIXME print progress
                    if(iter_num % int(tot_iter/20) == 0):
                        #print("searching: {}% done".format(int(iter_num/tot_iter*100)), sep=' ', end='\r', flush=True)
                        print("searching: {}% done".format(float(iter_num)/float(tot_iter)*100))
                    iter_num += 1

                    if poss in tempUsername:
                        num = (r_serv_cred.hget(REDIS_KEY_ALL_CRED_SET, tempUsername))
                        if num is not None:
                            uniq_num_set.add(num)
                        for num in r_serv_cred.smembers(tempUsername):
                            uniq_num_set.add(num)

    data = {'usr': [], 'path': [], 'numPaste': [], 'simil': []}
    for Unum in uniq_num_set:
        levenRatio = 2.0
        username = (r_serv_cred.hget(REDIS_KEY_ALL_CRED_SET_REV, Unum))

        # Calculate Levenshtein distance, ignore negative ratio
        supp_splitted = supplied.split()
        supp_mixed = supplied.replace(' ','')
        supp_splitted.append(supp_mixed)
        for indiv_supplied in supp_splitted:
            levenRatio = float(Levenshtein.ratio(indiv_supplied, username))
            levenRatioStr = "{:.1%}".format(levenRatio)

        data['usr'].append(username)


        allPathNum = list(r_serv_cred.smembers(REDIS_KEY_MAP_CRED_TO_PATH+'_'+Unum))

        data['path'].append(allPathNum)
        data['numPaste'].append(len(allPathNum))
        data['simil'].append(levenRatioStr)

    to_return = {}
    to_return["section"] = section
    to_return["action"] = action
    to_return["term"] = supplied
    to_return["data"] = data

    return jsonify(to_return)


# ========= REGISTRATION =========
app.register_blueprint(terms, url_prefix=baseUrl)

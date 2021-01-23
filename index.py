import time
import os
import smtplib
import datetime
import json
import logging
import requests

from email.mime.text import MIMEText

from login import CampusCard


def initLogging():
    logging.getLogger().setLevel(logging.INFO)
    logging.basicConfig(format="[%(levelname)s]; %(message)s")


def get_token(username, password):
    """
    获取用户令牌，模拟登录获取：https://github.com/zhongbr/wanmei_campus
    :param username: 账号
    :param password: 密码
    :return:
    """
    for _ in range(10):
        user_dict = CampusCard(username, password).user_info
        if user_dict["login"]:
            return user_dict["sessionId"]
        elif user_dict['login_msg']['message_'] == "该手机号未注册完美校园":
            return None
        elif user_dict['login_msg']['message_'].startswith("密码错误"):
            return None
        else:
            logging.warning('正在尝试重新登录......')
            time.sleep(5)
    return None


def get_school_name(token):
    post_data = {"token": token, "method": "WX_BASE_INFO", "param": "%7B%7D"}
    headers = {"Content-Type": "application/x-www-form-urlencoded"}
    try:
        res = requests.post(
            "https://server.59wanmei.com/YKT_Interface/xyk",
            data=post_data,
            headers=headers,
        )
        return res.json()["data"]["customerName"]
    except:
        return "泪目，没获取到学校名字"


def get_user_info(token):
    """
    用来获取custom_id，即类似与打卡模板id
    :param token: 用户令牌
    :return: return
    """
    data = {"appClassify": "DK", "token": token}
    for _ in range(3):
        try:
            res = requests.post(
                "https://reportedh5.17wanxiao.com/api/clock/school/getUserInfo", data=data
            )
            user_info = res.json()["userInfo"]
            logging.info('获取个人信息成功')
            return user_info
        except:
            logging.warning('获取个人信息失败，正在重试......')
            time.sleep(1)
    return None


def get_post_json(post_json, user_info):
    """
    获取打卡数据
    :param jsons: 用来获取打卡数据的json字段
    :return:
    """
    for _ in range(3):
        try:
            res = requests.post(
                url="https://reportedh5.17wanxiao.com/sass/api/epmpics",
                json=post_json,
                timeout=10,
            ).json()
        # print(res)
        except:
            logging.warning("获取完美校园打卡post参数失败，正在重试...")
            time.sleep(1)
            continue
        if res["code"] != "10000":
            # logging.warning(res)
            return None
        data = json.loads(res["data"])
        # print(data)
        post_dict = {
            "areaStr": data["areaStr"],
            "deptStr": {
                "deptid": user_info["classId"],
                "text": user_info["classDescription"],
            },
            "deptid": user_info["classId"],
            "customerid": user_info["customerId"],
            "userid": str(user_info["userId"]),
            "username": user_info["username"],
            "stuNo": user_info["stuNo"],
            "phonenum": data["phonenum"],
            "templateid": data["templateid"],
            "updatainfo": [
                {"propertyname": i["propertyname"], "value": i["value"]}
                for i in data["cusTemplateRelations"]
            ],
            "updatainfo_detail": [
                {
                    "propertyname": i["propertyname"],
                    "checkValues": i["checkValues"],
                    "description": i["decription"],
                    "value": i["value"],
                }
                for i in data["cusTemplateRelations"]
            ],
            "checkbox": [
                {"description": i["decription"], "value": i["value"]}
                for i in data["cusTemplateRelations"]
            ],
        }
        # print(json.dumps(post_dict, sort_keys=True, indent=4, ensure_ascii=False))
        logging.info("获取完美校园打卡post参数成功")
        return post_dict
    return None


def healthy_check_in(token, username, post_dict):
    """
    第一类健康打卡
    :param username: 手机号
    :param token: 用户令牌
    :param post_dict: 打卡数据
    :return:
    """
    check_json = {
        "businessType": "epmpics",
        "method": "submitUpInfo",
        "jsonData": {
            "deptStr": post_dict["deptStr"],
            "areaStr": post_dict["areaStr"],
            "reportdate": round(time.time() * 1000),
            "customerid": post_dict["customerid"],
            "deptid": post_dict["deptid"],
            "source": "app",
            "templateid": post_dict["templateid"],
            "stuNo": post_dict["stuNo"],
            "username": post_dict["username"],
            "phonenum": username,
            "userid": post_dict["userid"],
            "updatainfo": post_dict["updatainfo"],
            "gpsType": 1,
            "token": token,
        },
    }
    try:
        res = requests.post(
            "https://reportedh5.17wanxiao.com/sass/api/epmpics", json=check_json
        ).json()
        # 以json格式打印json字符串
        logging.info(res)
        return {
            "status": 1,
            "res": res,
            "post_dict": post_dict,
            "check_json": check_json,
            "type": "healthy",
        }
    except:
        errmsg = f"```打卡请求出错```"
        logging.warning("校内打卡请求出错")
        return {"status": 0, "errmsg": errmsg}


def get_recall_data(token):
    """
    获取第二类健康打卡的打卡数据
    :param token: 用户令牌
    :return: 返回dict数据
    """
    for _ in range(3):
        try:
            res = requests.post(
                url="https://reportedh5.17wanxiao.com/api/reported/recall",
                data={"token": token},
                timeout=10,
            ).json()
        except:
            logging.warning("获取完美校园打卡post参数失败，正在重试...")
            time.sleep(1)
            continue
        if res["code"] == 0:
            logging.info("获取完美校园打卡post参数成功")
            return res["data"]
        return None
    return None


def receive_check_in(token, custom_id, post_dict):
    """
    第二类健康打卡
    :param token: 用户令牌
    :param custom_id: 健康打卡id
    :param post_dict: 健康打卡数据
    :return:
    """
    check_json = {
        "userId": post_dict["userId"],
        "name": post_dict["name"],
        "stuNo": post_dict["stuNo"],
        "whereabouts": post_dict["whereabouts"],
        "familyWhereabouts": "",
        "beenToWuhan": post_dict["beenToWuhan"],
        "contactWithPatients": post_dict["contactWithPatients"],
        "symptom": post_dict["symptom"],
        "fever": post_dict["fever"],
        "cough": post_dict["cough"],
        "soreThroat": post_dict["soreThroat"],
        "debilitation": post_dict["debilitation"],
        "diarrhea": post_dict["diarrhea"],
        "cold": post_dict["cold"],
        "staySchool": post_dict["staySchool"],
        "contacts": post_dict["contacts"],
        "emergencyPhone": post_dict["emergencyPhone"],
        "address": post_dict["address"],
        "familyForAddress": "",
        "collegeId": post_dict["collegeId"],
        "majorId": post_dict["majorId"],
        "classId": post_dict["classId"],
        "classDescribe": post_dict["classDescribe"],
        "temperature": post_dict["temperature"],
        "confirmed": post_dict["confirmed"],
        "isolated": post_dict["isolated"],
        "passingWuhan": post_dict["passingWuhan"],
        "passingHubei": post_dict["passingHubei"],
        "patientSide": post_dict["patientSide"],
        "patientContact": post_dict["patientContact"],
        "mentalHealth": post_dict["mentalHealth"],
        "wayToSchool": post_dict["wayToSchool"],
        "backToSchool": post_dict["backToSchool"],
        "haveBroadband": post_dict["haveBroadband"],
        "emergencyContactName": post_dict["emergencyContactName"],
        "helpInfo": "",
        "passingCity": "",
        "longitude": "",  # 请在此处填写需要打卡位置的longitude
        "latitude": "",  # 请在此处填写需要打卡位置的latitude
        "token": token,
    }
    headers = {
        "referer": f"https://reportedh5.17wanxiao.com/nCovReport/index.html?token={token}&customerId={custom_id}",
        "content-type": "application/x-www-form-urlencoded;charset=UTF-8",
    }
    try:
        res = requests.post(
            "https://reportedh5.17wanxiao.com/api/reported/receive",
            headers=headers,
            data=check_json,
        ).json()
        # 以json格式打印json字符串
        # print(res)
        if res["code"] == 0:
            logging.info(res)
            return dict(
                status=1,
                res=res,
                post_dict=post_dict,
                check_json=check_json,
                type="healthy",
            )
        else:
            logging.warning(res)
            return dict(
                status=1,
                res=res,
                post_dict=post_dict,
                check_json=check_json,
                type="healthy",
            )
    except:
        errmsg = f"```打卡请求出错```"
        logging.warning("打卡请求出错，网络不稳定")
        return dict(status=0, errmsg=errmsg)


def get_ap():
    """
    获取当前时间，用于校内打卡
    :return: 返回布尔列表：[am, pm, ev]
    """
    now_time = datetime.datetime.utcnow() + datetime.timedelta(hours=8)
    am = 0 <= now_time.hour < 12
    pm = 12 <= now_time.hour < 17
    ev = 17 <= now_time.hour <= 23
    return [am, pm, ev]


def get_id_list(token, custom_id):
    """
    通过校内模板id获取校内打卡具体的每个时间段id
    :param token: 用户令牌
    :param custom_id: 校内打卡模板id
    :return: 返回校内打卡id列表
    """
    post_data = {
        "customerAppTypeId": custom_id,
        "longitude": "",
        "latitude": "",
        "token": token,
    }
    try:
        res = requests.post(
            "https://reportedh5.17wanxiao.com/api/clock/school/rules", data=post_data
        )
        # print(res.text)
        return res.json()["customerAppTypeDto"]["ruleList"]
    except:
        return None


def get_id_list_v1(token):
    """
    通过校内模板id获取校内打卡具体的每个时间段id（初版,暂留）
    :param token: 用户令牌
    :return: 返回校内打卡id列表
    """
    post_data = {"appClassify": "DK", "token": token}
    try:
        res = requests.post(
            "https://reportedh5.17wanxiao.com/api/clock/school/childApps",
            data=post_data,
        )
        if res.json()["appList"]:
            id_list = sorted(
                res.json()["appList"][-1]["customerAppTypeRuleList"],
                key=lambda x: x["id"],
            )
            res_dict = [
                {"id": j["id"], "templateid": f"clockSign{i + 1}"}
                for i, j in enumerate(id_list)
            ]
            return res_dict
        return None
    except:
        return None


def campus_check_in(username, token, post_dict, id):
    """
    校内打卡
    :param username: 电话号
    :param token: 用户令牌
    :param post_dict: 校内打卡数据
    :param id: 校内打卡id
    :return:
    """
    check_json = {
        "businessType": "epmpics",
        "method": "submitUpInfoSchool",
        "jsonData": {
            "deptStr": post_dict["deptStr"],
            "areaStr": post_dict["areaStr"],
            "reportdate": round(time.time() * 1000),
            "customerid": post_dict["customerid"],
            "deptid": post_dict["deptid"],
            "source": "app",
            "templateid": post_dict["templateid"],
            "stuNo": post_dict["stuNo"],
            "username": post_dict["username"],
            "phonenum": username,
            "userid": post_dict["userid"],
            "updatainfo": post_dict["updatainfo"],
            "customerAppTypeRuleId": id,
            "clockState": 0,
            "token": token,
        },
        "token": token,
    }
    # print(check_json)
    try:
        res = requests.post(
            "https://reportedh5.17wanxiao.com/sass/api/epmpics", json=check_json
        ).json()

        # 以json格式打印json字符串
        if res["code"] != "10000":
            logging.warning(res)
            return dict(
                status=1,
                res=res,
                post_dict=post_dict,
                check_json=check_json,
                type=post_dict["templateid"],
            )
        else:
            logging.info(res)
            return dict(
                status=1,
                res=res,
                post_dict=post_dict,
                check_json=check_json,
                type=post_dict["templateid"],
            )
    except BaseException:
        errmsg = f"```校内打卡请求出错```"
        logging.warning("校内打卡请求出错")
        return dict(status=0, errmsg=errmsg)


def check_in(username, password):
    # 登录获取token用于打卡
    token = get_token(username, password)
    # print(token)
    check_dict_list = []
    # 获取现在是上午，还是下午，还是晚上
    # ape_list = get_ap()

    # 获取学校使用打卡模板Id
    user_info = get_user_info(token)

    if not token:
        errmsg = f"{username[:4]}，获取token失败，打卡失败"
        logging.warning(errmsg)
        check_dict_list.append({"status": 0, "errmsg": errmsg})
        return check_dict_list

    # 获取第一类健康打卡的参数
    json1 = {
        "businessType": "epmpics",
        "jsonData": {"templateid": "pneumonia", "token": token},
        "method": "userComeApp",
    }
    post_dict = get_post_json(json1, user_info)

    if post_dict:
        # 第一类健康打卡
        # print(post_dict)

        # 修改温度等参数
        # for j in post_dict['updatainfo']:  # 这里获取打卡json字段的打卡信息，微信推送的json字段
        #     if j['propertyname'] == 'temperature':  # 找到propertyname为temperature的字段
        #         j['value'] = '36.2'  # 由于原先为null，这里直接设置36.2（根据自己学校打卡选项来）
        #     if j['propertyname'] == '举一反三即可':
        #         j['value'] = '举一反三即可'

        # 修改地址，依照自己完美校园，查一下地址即可
        # post_dict['areaStr'] = '{"streetNumber":"89号","street":"建设东路","district":"","city":"新乡市","province":"河南省",' \
        #                        '"town":"","pois":"河南师范大学(东区)","lng":113.91572178314209,' \
        #                        '"lat":35.327695868943984,"address":"牧野区建设东路89号河南师范大学(东区)","text":"河南省-新乡市",' \
        #                        '"code":""} '
        healthy_check_dict = healthy_check_in(token, username, post_dict)
        check_dict_list.append(healthy_check_dict)
    else:
        # 获取第二类健康打卡参数
        post_dict = get_recall_data(token)
        # 第二类健康打卡
        healthy_check_dict = receive_check_in(token, user_info["customerId"], post_dict)
        check_dict_list.append(healthy_check_dict)

    # # 获取校内打卡ID
    # id_list = get_id_list(token, user_info.get('customerAppTypeId'))
    # # print(id_list)
    # if not id_list:
    #     return check_dict_list
    #
    # # 校内打卡
    # for index, i in enumerate(id_list):
    #     if ape_list[index]:
    #         # print(i)
    #         logging.info(f"-------------------------------{i['templateid']}-------------------------------")
    #         json2 = {"businessType": "epmpics",
    #                  "jsonData": {"templateid": i['templateid'], "customerAppTypeRuleId": i['id'],
    #                               "stuNo": post_dict['stuNo'],
    #                               "token": token}, "method": "userComeAppSchool",
    #                  "token": token}
    #         campus_dict = get_post_json(json2, user_info)
    #         campus_dict['areaStr'] = post_dict['areaStr']
    #         for j in campus_dict['updatainfo']:
    #             if j['propertyname'] == 'temperature':
    #                 j['value'] = '36.4'
    #             if j['propertyname'] == 'symptom':
    #                 j['value'] = '无症状'
    #         campus_check_dict = campus_check_in(username, token, campus_dict, i['id'])
    #         check_dict_list.append(campus_check_dict)
    #         logging.info("--------------------------------------------------------------")
    return check_dict_list


def server_push(sckey, desp):
    """
    Server酱推送：https://sc.ftqq.com/3.version
    :param sckey: 通过官网注册获取，获取教程：https://github.com/ReaJason/17wanxiaoCheckin-Actions/blob/master/README_LAST.md#%E4%BA%8Cserver%E9%85%B1%E6%9C%8D%E5%8A%A1%E7%9A%84%E7%94%B3%E8%AF%B7
    :param desp: 需要推送的内容
    :return:
    """
    bj_time = datetime.datetime.utcnow() + datetime.timedelta(hours=8)
    date_time = bj_time.strftime("%m-%d")
    send_url = f"https://sc.ftqq.com/{sckey}.send"
    params = {"text":"打卡", "desp": desp}
    # 发送消息
    for _ in range(3):
        try:
            res = requests.post(send_url, data=params)
            if not res.json()["errno"]:
                logging.info("Server酱推送服务成功")
                break
            else:
                logging.warning("Server酱推送服务失败")
                break
        except:
            time.sleep(1)
            logging.warning("Server酱不起作用了，可能是你的sckey出现了问题也可能服务器波动了，正在重试......")


def qq_mail_push(send_email, send_pwd, receive_email, check_info_list):
    bj_time = datetime.datetime.utcnow() + datetime.timedelta(hours=8)
    bj_time.strftime("%Y-%m-%d %H:%M:%S %p")
    mail_msg_list = [f"""
<h2><center> >>>>  <a href="https://github.com/ReaJason/17wanxiaoCheckin-Actions">17wanxiaoCheckin-Actions</a>
<<<<</center></h2>
<h2><center>期待你的Star✨</center></h2>
<h3><center>打卡时间：{bj_time}</center></h3>
"""
    ]
    for check in check_info_list:
        if check["status"]:
            name = check['post_dict'].get('username')
            if not name:
                name = check['post_dict']['name']
            mail_msg_list.append(f"""<hr>
<details>
<summary style="font-family: 'Microsoft YaHei UI',serif; color: deepskyblue;">{name}：{check["type"]} 打卡结果：{check['res']}</summary>
<pre><code>
{json.dumps(check['check_json'], sort_keys=True, indent=4, ensure_ascii=False)}
</code></pre>
</details>
<details>
<summary style="font-family: 'Microsoft YaHei UI',serif; color: black;" >>>>填写数据抓包详情（便于代码的编写）<<<</summary>
<pre><code>
{json.dumps(check['post_dict']['updatainfo_detail'], sort_keys=True, indent=4, ensure_ascii=False)}
</code></pre>
</details>
<details>
<summary style="font-family: 'Microsoft YaHei UI',serif; color: lightskyblue;" >>>>打卡信息数据表格<<<</summary>
<table id="customers">
<tr>
<th>Text</th>
<th>Value</th>
</tr>
"""
            )
            for index, box in enumerate(check["post_dict"]["checkbox"]):
                if index % 2:
                    mail_msg_list.append(
                        f"""<tr>
<td>{box['description']}</td>
<td>{box['value']}</td>
</tr>"""
                    )
                else:
                    mail_msg_list.append(f"""<tr class="alt">
<td>{box['description']}</td>
<td>{box['value']}</td>
</tr>"""
                                         )
            mail_msg_list.append(
                f"""
</table></details>"""
            )
        else:
            mail_msg_list.append(
                f"""<hr>
    <b style="color: red">{check['errmsg']}</b>"""
            )
    css = """<style type="text/css">
#customers
  {
  font-family:"Trebuchet MS", Arial, Helvetica, sans-serif;
  width:100%;
  border-collapse:collapse;
  }

#customers td, #customers th 
  {
  font-size:1em;
  border:1px solid #98bf21;
  padding:3px 7px 2px 7px;
  }

#customers th 
  {
  font-size:1.1em;
  text-align:left;
  padding-top:5px;
  padding-bottom:4px;
  background-color:#A7C942;
  color:#ffffff;
  }

#customers tr.alt td 
  {
  color:#000000;
  background-color:#EAF2D3;
  }
</style>"""
    mail_msg_list.append(css)
    msg = MIMEText("".join(mail_msg_list), "html", "utf-8")
    msg["From"] = send_email
    msg["To"] = receive_email
    msg["Subject"] = "完美校园健康打卡推送"
    try:
        with smtplib.SMTP_SSL("smtp.qq.com", 465) as server:
            server.login(send_email, send_pwd)  # 括号中对应的是发件人邮箱账号、邮箱密码
            server.sendmail(
                send_email,
                [
                    receive_email,
                ],
                msg.as_string(),
            )  # 括号中对应的是发件人邮箱账号、收件人邮箱账号、发送邮件
            logging.info('qq邮箱推送成功')

    except Exception as e:
        logging.warning(f'qq邮箱推送失败：{e}')


def main_handler(*args, **kwargs):
    initLogging()
    bj_time = datetime.datetime.utcnow() + datetime.timedelta(hours=8)
    log_info = [
        f"""
------
#### 现在时间：
```
{bj_time.strftime("%Y-%m-%d %H:%M:%S %p")}
```"""]
    raw_info = []
    username_list = os.environ['USERNAME'].split(',')
    password_list = os.environ['PASSWORD'].split(',')
    sckey = os.environ['SCKEY']
    send_email = os.environ.get('SEND_EMAIL')
    send_pwd = os.environ.get('SEND_PWD')
    receive_email = os.environ.get('RECEIVE_EMAIL')
    for username, password in zip([i.strip() for i in username_list if i != ''],
                                  [i.strip() for i in password_list if i != '']):
        check_dict = check_in(username, password)
        raw_info.extend(check_dict)
        if not check_dict:
            return
        else:
            for check in check_dict:
                if check["status"]:
                    if check["post_dict"].get("checkbox"):
                        post_msg = "\n".join(
                            [
                                f"| {i['description']} | {i['value']} |"
                                for i in check["post_dict"].get("checkbox")
                            ]
                        )
                    else:
                        post_msg = "暂无详情"
                    name = check['post_dict'].get('username')
                    if not name:
                        name = check['post_dict']['name']
                    log_info.append(
                        f"""#### {name}{check['type']}打卡信息：
```
{json.dumps(check['check_json'], sort_keys=True, indent=4, ensure_ascii=False)}
```

------
| Text                           | Message |
| :----------------------------------- | :--- |
{post_msg}
------
```
{check['res']}
```"""
                    )
                    # log_info.append(
                    #     f"""
# ```
# {json.dumps(check['post_dict']['updatainfo_detail'], sort_keys=True, indent=4, ensure_ascii=False)}
# ```"""
#                     )
                else:
                    log_info.append(
                        f"""------
#### {check['errmsg']}
------
"""
                    )
    log_info.append(
        f"""
>
> 
"""
    )
    if sckey:
        server_push(sckey, "\n".join(log_info))
    if send_email and send_pwd and receive_email:
        qq_mail_push(send_email, send_pwd, receive_email, raw_info)


if __name__ == "__main__":
    main_handler()

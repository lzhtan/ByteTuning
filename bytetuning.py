# coding=utf-8
# 文件名：watermark.py
# 作者：谭立状
# 描述：无损网络下交换机水线配置的自适应调优，输出最优水线配置参数
# 修改人：谭立状
# 修改时间：2021-06-22
# 版本号：v0.1

from os import POSIX_FADV_NORMAL
from time import time_ns
from netmiko import ConnectHandler
from requests.api import head #配置交换机
import requests
import datetime
import json
import numpy as np
import csv
import time
import os
import yaml
import argparse
import sys
import math
import random


os.system('cp -r result old_result/result_' + str(int(time.time())) +' && rm -rf result') #清理result内容


#解析输入指令
parser = argparse.ArgumentParser(description='ByteDance RDMA watermark autotuning system...')
parser.add_argument('-f', '-filenameforconfig', action="store", help="配置文件路径，默认为./config/config.yaml", dest="config_file_name", type=str)      #配置文件目录
parser.add_argument('-r', '-recovery', action="store", help="恢复模式，默认为0。置1则恢复交换机默认水线，置0则调优模式，", dest="recovery_flag", type=int)     #恢复模式
args = parser.parse_args()

if args.config_file_name is None:
    tuning_config_filename = "./config/config.yaml"
else:
    tuning_config_filename = args.config_file_name   #读取配置文件目录

if args.recovery_flag is None:
    tuning_recovery_flag = 0
else:
    tuning_recovery_flag = args.recovery_flag   #读取恢复模式，若标志位置1，则恢复交换机水线配置至默认配置

yaml_obj = open(tuning_config_filename, "r")    #读取yaml配置文件，纪录有交换机信息、交换机登陆信息、交换机端口信息、调优参数信息
tuning_config_file_yaml = yaml.load(yaml_obj, Loader=yaml.FullLoader)


tuning_mode = tuning_config_file_yaml['tuning_mode']                               #读取调优策略，0为遍历搜索，1为集中调优
tuning_result_file_path = tuning_config_file_yaml['result_file_path']              #读取调优结果文件路径
if not os.path.exists(tuning_result_file_path):
        os.mkdir(tuning_result_file_path)
max_Leaf_ecn_highlimit = tuning_config_file_yaml['max_Leaf_ecn_highlimit']
max_Spine_ecn_highlimit = tuning_config_file_yaml['max_Spine_ecn_highlimit']
max_ecn_probility = tuning_config_file_yaml['max_ecn_probility']
max_ingress_pfc_alpha = tuning_config_file_yaml['max_ingress_pfc_alpha'] 
max_Leaf_pfc_headroom = tuning_config_file_yaml['max_Leaf_pfc_headroom']
max_Spine_pfc_headroom = tuning_config_file_yaml['max_Spine_pfc_headroom']

init_Leaf_ecn_highlimit = tuning_config_file_yaml['init_Leaf_ecn_highlimit']
init_Spine_ecn_highlimit = tuning_config_file_yaml['init_Spine_ecn_highlimit']
init_Leaf_ecn_lowlimit = tuning_config_file_yaml['init_Leaf_ecn_lowlimit']
init_Spine_ecn_lowlimit = tuning_config_file_yaml['init_Spine_ecn_lowlimit']
init_ecn_probility = tuning_config_file_yaml['init_ecn_probility']
init_Leaf_ingress_pfc_alpha = tuning_config_file_yaml['init_Leaf_ingress_pfc_alpha']
init_Spine_ingress_pfc_alpha = tuning_config_file_yaml['init_Spine_ingress_pfc_alpha']
init_Leaf_pfc_headroom = tuning_config_file_yaml['init_Leaf_pfc_headroom']
init_Spine_pfc_headroom = tuning_config_file_yaml['init_Spine_pfc_headroom']

switch_information = tuning_config_file_yaml['switch_information']                                                                            #调优交换机基本信息
switch_number = len(switch_information)                                                                                                       #调优交换机总数量
all_egress_num = sum([len(arr) for arr in ([x[field] for x in switch_information for field in ['egress_port'] if x[field] is not None])])     #调优egress接口总数量
all_ingress_num = sum([len(arr) for arr in ([x[field] for x in switch_information for field in ['ingress_port'] if x[field] is not None])])   #调优ingress接口总数量

#读取集中调优算法参数
step_length = tuning_config_file_yaml['step_length_init']                                                   #调优步长
parameter_tuning_number = tuning_config_file_yaml['parameter_tuning_number']                                #同时调优参数数量：越大，则广度搜索能力越强；越小，则深度搜索能力越强
first_step_init = tuning_config_file_yaml['first_step_init']                                                #初始解构造
max_iteration = tuning_config_file_yaml['max_iteration']                                                    #最大迭代次数，退出条件
iteration = 0
throughput_weight = tuning_config_file_yaml['throughput_weight']                                            #吞吐权重
latency_weight = tuning_config_file_yaml['latency_weight']                                                  #延迟权重
telemetry_duration = tuning_config_file_yaml['telemetry_duration']                                          #分钟平均值作为吞吐或者队列测量结果
tuning_parameter_number = tuning_config_file_yaml['tuning_parameter_number']                                #调优参数，一般是5个，ECN三个，PFC两个 

#集中调优初始化解
bytetuning_parameter_every_epoch = [[init_Leaf_ecn_lowlimit, init_Leaf_ecn_highlimit, init_ecn_probility, init_Leaf_ingress_pfc_alpha, init_Leaf_pfc_headroom] * all_ingress_num for row in range(max_iteration+1)] #包含all_ingress_num * tuning_parameter_number个参数
max_bytetuning_parameter_every_epoch = [max_Leaf_ecn_highlimit, max_Leaf_ecn_highlimit, max_ecn_probility, max_ingress_pfc_alpha, max_Leaf_pfc_headroom] * all_ingress_num #调优搜索空间

#存储每一轮的吞吐和队列结果
sys_throughput_every_epoch = [[0] for row in range(max_iteration+1)]                         #每轮最优吞吐
sys_queue_every_epoch = [[0] for row in range(max_iteration+1)]                              #每轮最优队列长度
step_length_epoch = [[step_length] for row in range(max_iteration)]                          #调优步长

#打印项目Logo
def start_print_logo():
    file_object = open("./bytetuning_logo.log")
    try:
        all_the_text = file_object.read()
    finally:
        file_object.close()
    print(all_the_text)

#交换机登陆配置，仅给出通过username和password登录交换机的基础示例，请根据实际情况配置
switch_ssh = {
    'device_type':'',
    'username':tuning_config_file_yaml['switch_ssh_username'],
    'ip':'',
    'password':tuning_config_file_yaml['switch_ssh_password'],
}

#交换机设备名称转换
def switch_device_type(switch_brand):
    if switch_brand == 'H3C':
        return 'hp_comware'
    if switch_brand == 'Huawei':
        return 'huawei'
    if switch_brand == 'Arista':
        return 'arista_eos'
    if switch_brand == 'Ruijie':
        return 'ruijie_os'

#水线计算函数：计算生成新水线，返回ECN低水线ECN_LowLimit、ECN高水线ECN_HighLimit、ECN标记概率ECN_Probility、PFC水线PFC_Limit、阿尔法值Alpha、PFC_Headroom
def bytetuning_best_watermark():
    print("  【系统信息】当前调优策略为：集中调优")
    print('  【调优信息】初始解为：' + str(bytetuning_parameter_every_epoch[0][:]))
    print('  【调优信息】搜索空间为：' + str(max_bytetuning_parameter_every_epoch[:]))
    f_bytetuning_parameter_every_epoch = tuning_result_file_path + "/bytetuning_parameter_every_epoch_result.csv"
    f_sys_best_throughput_every_epoch = tuning_result_file_path + "/bytetuning_best_throughput_every_epoch_result.csv"
    f_sys_best_queue_every_epoch = tuning_result_file_path + "/bytetuning_best_queue_every_epoch_result.csv"
    f_sys_better_throughput_every_epoch = tuning_result_file_path + "/bytetuning_better_throughput_every_epoch_result.csv"
    f_sys_better_queue_every_epoch = tuning_result_file_path + "/bytetuning_better_queue_every_epoch_result.csv"
    f_sys_throughput_every_time = tuning_result_file_path + "/bytetuning_throughput_every_time_result.csv"
    f_sys_queue_every_time = tuning_result_file_path + "/bytetuning_queue_every_time_result.csv"
    if os.path.exists(f_bytetuning_parameter_every_epoch):  #清理旧调优结果
        os.remove(f_bytetuning_parameter_every_epoch)  
        with open(f_bytetuning_parameter_every_epoch,'w') as csvfile:
            writer = csv.writer(csvfile, delimiter=' ')
            writer.writerow(['iteration','parameter'])   
    if os.path.exists(f_sys_best_throughput_every_epoch):  #清理旧调优结果
        os.remove(f_sys_best_throughput_every_epoch)  
        with open(f_sys_best_throughput_every_epoch,'w') as csvfile:
            writer = csv.writer(csvfile, delimiter=' ')
            writer.writerow(['iteration','throughput'])      
    if os.path.exists(f_sys_best_queue_every_epoch):  #清理旧调优结果
        os.remove(f_sys_best_queue_every_epoch)  
        with open(f_sys_best_queue_every_epoch,'w') as csvfile:
            writer = csv.writer(csvfile, delimiter=' ')
            writer.writerow(['iteration','queue']) 
    global iteration
    global step_length
    for iteration in range(max_iteration):
        ingress_number = 0
        print('   -----------------------------------------------') 
        print('  【系统信息】当前进行到第' + str(iteration) + '轮')
        if iteration == 0:
            for switch_item in switch_information:
                for ingress_item in switch_item["ingress_port"]:
                    ecn_lowlimit = bytetuning_parameter_every_epoch[0][ingress_number] 
                    ecn_highlimit = bytetuning_parameter_every_epoch[0][ingress_number + 1]
                    ecn_probility = bytetuning_parameter_every_epoch[0][ingress_number + 2]
                    alpha = bytetuning_parameter_every_epoch[0][ingress_number + 3]
                    headroom =  bytetuning_parameter_every_epoch[0][ingress_number + 4]
                    set_new_watermark_for_bytetuning(switch_item["switch_ip"],switch_item["vendor_name"],ingress_item,headroom,alpha,ecn_lowlimit,ecn_highlimit,ecn_probility)
                    ingress_number = ingress_number + 5
            time.sleep(70*telemetry_duration) #等待若干秒再查询交换机metrics，因为metrics更新较慢
            sys_throughput_every_epoch[max_iteration] =  get_all_switch_egress_throughput() #收集吞吐
            sys_queue_every_epoch[max_iteration] = get_all_switch_ingress_queue() #收集出口队列
            sys_throughput_every_epoch[0] =  sys_throughput_every_epoch[max_iteration] #收集吞吐
            sys_queue_every_epoch[0] = sys_queue_every_epoch[max_iteration] #收集出口队列
            bytetuning_parameter_every_epoch[max_iteration][:] = bytetuning_parameter_every_epoch[0][:]
            with open(f_sys_throughput_every_time,'a') as csvfile:
                writer = csv.writer(csvfile, delimiter=' ')
                writer.writerow([str(int(time.time())), sys_throughput_every_epoch[max_iteration]])
            with open(f_sys_queue_every_time,'a') as csvfile:
                writer = csv.writer(csvfile, delimiter=' ')
                writer.writerow([str(int(time.time())), sys_queue_every_epoch[max_iteration]])
        else:
            #暂时将上一轮水线配置方案保存到本轮
            bytetuning_parameter_every_epoch[iteration][:] = bytetuning_parameter_every_epoch[iteration - 1][:]
            sys_throughput_every_epoch[max_iteration] =  sys_throughput_every_epoch[iteration - 1]
            sys_queue_every_epoch[max_iteration] = sys_queue_every_epoch[iteration - 1]
            sys_throughput_every_epoch[iteration] =  sys_throughput_every_epoch[iteration - 1]
            sys_queue_every_epoch[iteration] = sys_queue_every_epoch[iteration - 1]
            #下发2 * all_ingress_num * tuning_parameter_number 种新情况的水线配置，收集其吞吐变化
            for i in range(2 * all_ingress_num * tuning_parameter_number):
                print('  【系统信息】当前进行到第' + str(iteration) + '轮第' + str(i) +'次探测')
                ingress_number = 0
                bytetuning_parameter_every_epoch[max_iteration][:] = bytetuning_parameter_every_epoch[iteration - 1][:]
                if (i % 2) == 0: # 向下取整，如果超出搜索范围，则保持不变
                    for tuning_parameter_number_i in random.sample(range(all_ingress_num * tuning_parameter_number), tuning_parameter_number):
                        if math.floor(bytetuning_parameter_every_epoch[max_iteration][math.floor(i/2)] + bytetuning_parameter_every_epoch[max_iteration][math.floor(i/2)] * step_length) <= max_bytetuning_parameter_every_epoch[math.floor(i/2)]:
                            bytetuning_parameter_every_epoch[max_iteration][math.floor(i/2)] = math.floor(bytetuning_parameter_every_epoch[max_iteration][math.floor(i/2)] + bytetuning_parameter_every_epoch[max_iteration][math.floor(i/2)] * step_length)
                        if math.floor(i/2) != tuning_parameter_number_i:
                            if math.floor(bytetuning_parameter_every_epoch[max_iteration][tuning_parameter_number_i] + bytetuning_parameter_every_epoch[0][tuning_parameter_number_i] * step_length) <= max_bytetuning_parameter_every_epoch[tuning_parameter_number_i]:
                                bytetuning_parameter_every_epoch[max_iteration][tuning_parameter_number_i] = math.floor(bytetuning_parameter_every_epoch[max_iteration][tuning_parameter_number_i] + bytetuning_parameter_every_epoch[max_iteration][tuning_parameter_number_i] * step_length)
                else:
                    for tuning_parameter_number_i in random.sample(range(all_ingress_num * tuning_parameter_number), tuning_parameter_number):
                        if math.floor(bytetuning_parameter_every_epoch[max_iteration][math.floor(i/2)] - bytetuning_parameter_every_epoch[max_iteration][math.floor(i/2)] * step_length) >= 2:
                            bytetuning_parameter_every_epoch[max_iteration][math.floor(i/2)] = math.floor(bytetuning_parameter_every_epoch[max_iteration][math.floor(i/2)] - bytetuning_parameter_every_epoch[max_iteration][math.floor(i/2)] * step_length)
                        if math.floor(i/2) != tuning_parameter_number_i:
                            if math.floor(bytetuning_parameter_every_epoch[max_iteration][tuning_parameter_number_i] - bytetuning_parameter_every_epoch[0][tuning_parameter_number_i] * step_length) >= 2:
                                bytetuning_parameter_every_epoch[max_iteration][tuning_parameter_number_i] = math.floor(bytetuning_parameter_every_epoch[max_iteration][tuning_parameter_number_i] - bytetuning_parameter_every_epoch[max_iteration][tuning_parameter_number_i] * step_length)
                for switch_item in switch_information:
                    for ingress_item in switch_item["ingress_port"]:
                        ecn_lowlimit = bytetuning_parameter_every_epoch[max_iteration][ingress_number]
                        ecn_highlimit = bytetuning_parameter_every_epoch[max_iteration][ingress_number+1]
                        if ecn_highlimit <= ecn_lowlimit:
                            bytetuning_parameter_every_epoch[max_iteration][ingress_number] = bytetuning_parameter_every_epoch[0][ingress_number] 
                            ecn_lowlimit = bytetuning_parameter_every_epoch[max_iteration][ingress_number]
                            bytetuning_parameter_every_epoch[max_iteration][ingress_number+1] = bytetuning_parameter_every_epoch[0][ingress_number+1] 
                            ecn_highlimit = bytetuning_parameter_every_epoch[max_iteration][ingress_number+1]
                        ecn_probility = bytetuning_parameter_every_epoch[max_iteration][ingress_number+2]
                        alpha = bytetuning_parameter_every_epoch[max_iteration][ingress_number+3]
                        headroom =  bytetuning_parameter_every_epoch[max_iteration][ingress_number+4]
                        set_new_watermark_for_bytetuning(switch_item["switch_ip"],switch_item["vendor_name"],ingress_item,headroom,alpha,ecn_lowlimit,ecn_highlimit,ecn_probility)
                        ingress_number = ingress_number + 5
                time.sleep(70*telemetry_duration) #等待若干秒再查询交换机metrics，因为metrics更新较慢
                sys_throughput_now = get_all_switch_egress_throughput() #收集吞吐
                sys_queue_now = get_all_switch_ingress_queue() #收集出口队列
                with open(f_sys_throughput_every_time,'a') as csvfile:
                    writer = csv.writer(csvfile, delimiter=' ')
                    writer.writerow([str(int(time.time())), sys_throughput_now])
                with open(f_sys_queue_every_time,'a') as csvfile:
                    writer = csv.writer(csvfile, delimiter=' ')
                    writer.writerow([str(int(time.time())), sys_queue_now])
                if (throughput_weight * sys_throughput_now /(latency_weight * (sys_queue_now+1))) >= (throughput_weight * sys_throughput_every_epoch[max_iteration]/(latency_weight * (sys_queue_every_epoch[max_iteration]+1))): 
                    sys_throughput_every_epoch[max_iteration] =  sys_throughput_now
                    sys_queue_every_epoch[max_iteration] = sys_queue_now
                    sys_throughput_every_epoch[iteration] =  sys_throughput_now
                    sys_queue_every_epoch[iteration] = sys_queue_now
                    bytetuning_parameter_every_epoch[iteration][:] = bytetuning_parameter_every_epoch[max_iteration][:]
                    with open(f_sys_better_throughput_every_epoch,'a') as csvfile:
                        writer = csv.writer(csvfile, delimiter=' ')
                        writer.writerow([str(int(time.time())), sys_throughput_now])
                    with open(f_sys_better_queue_every_epoch,'a') as csvfile:
                        writer = csv.writer(csvfile, delimiter=' ')
                        writer.writerow([str(int(time.time())), sys_queue_now])
            if bytetuning_parameter_every_epoch[iteration][:] == bytetuning_parameter_every_epoch[iteration - 1][:]: #如果没有改善，则增大搜索步长；如果改善，则减小搜索步长。相当于认为全局只有一个最优点。
                if step_length * 2 <= 1:
                    step_length = step_length * 2
                else:
                    step_length = step_length_epoch[0]
            else:
                if step_length/2 > 0.01:
                    step_length = step_length/2
                else:
                    step_length = step_length_epoch[0] 
            step_length_epoch[iteration] = step_length
            print("第"+str(iteration)+"轮，水线参数为：")
            print(bytetuning_parameter_every_epoch[iteration][:])
        with open(f_bytetuning_parameter_every_epoch,'a') as csvfile:
            writer = csv.writer(csvfile, delimiter=' ')
            writer.writerow([str(iteration), bytetuning_parameter_every_epoch[iteration][:]])
        with open(f_sys_best_throughput_every_epoch,'a') as csvfile:
            writer = csv.writer(csvfile, delimiter=' ')
            writer.writerow([str(iteration), sys_throughput_every_epoch[iteration]])
        with open(f_sys_best_queue_every_epoch,'a') as csvfile:
            writer = csv.writer(csvfile, delimiter=' ')
            writer.writerow([str(iteration), sys_queue_every_epoch[iteration]])
    set_default_watermark()#记录初始默认水线配置结果
    sys_throughput_every_epoch[max_iteration] =  get_all_switch_egress_throughput() #收集吞吐
    sys_queue_every_epoch[max_iteration] = get_all_switch_ingress_queue() #收集入口队列
    with open(f_bytetuning_parameter_every_epoch,'a') as csvfile:
        writer = csv.writer(csvfile, delimiter=' ')
        writer.writerow(['experience-base watermark', 'experience-base watermark'])
    with open(f_sys_best_throughput_every_epoch,'a') as csvfile:
        writer = csv.writer(csvfile, delimiter=' ')
        writer.writerow(['experience-base watermark', sys_throughput_every_epoch[max_iteration]])
    with open(f_sys_best_queue_every_epoch,'a') as csvfile:
        writer = csv.writer(csvfile, delimiter=' ')
        writer.writerow(['experience-base watermark', sys_queue_every_epoch[max_iteration]])
       
def start_save_all_switch_configuration():
    for switch_item in switch_information:
        switch_ssh['ip'] = switch_item["switch_ip"]
        switch_ssh['device_type'] = switch_device_type(switch_item["vendor_name"])
        connect = ConnectHandler(**switch_ssh)
        output = connect.send_command('system view')
        output = connect.send_command('display current-configuration')
        tuning_switch_initial_configuration_filename = tuning_result_file_path + "/" + switch_item["switch_ip"] + "_initial_configuration.txt" 
        f = open(tuning_switch_initial_configuration_filename, "w+", encoding="utf-8") 
        f.write(output)
        f.close()
        print('  【系统信息】保存交换机[' + switch_item["switch_ip"] +']原始配置：' + tuning_switch_initial_configuration_filename)
    print('   -----------------------------------------------') 

#恢复默认水线配置并配置下发，仅给出H3C通用配置策略
def set_default_watermark():
    for switch_item in switch_information:
        switch_ssh['ip'] = switch_item["switch_ip"]
        switch_ssh['device_type'] = switch_device_type(switch_item["vendor_name"])
        connect = ConnectHandler(**switch_ssh)
        print('  【系统信息】成功连接到交换机[' + switch_item["switch_ip"] + ']')
        output = connect.send_command('system view')
        if switch_item["vendor_name"] == "H3C" and switch_item["switch_level"] == 'XX':
            config_commands = [
                        'qos wred queue table XXX',#XXX为表名，X为队列序号
                        'queue X drop-level X low-limit value high-limit value discard-probability value',
                        'queue X drop-level X low-limit value high-limit value discard-probability value',
                        'queue X drop-level X low-limit value high-limit value discard-probability value',
                        'qos wred queue table XXXX',#XXXX为表名
                        'queue X drop-level X low-limit value high-limit value discard-probability value',
                        'queue X drop-level X low-limit value high-limit value discard-probability value',
                        'queue X drop-level X low-limit value high-limit value discard-probability value',
                        ]
            output = connect.send_config_set(config_commands)
            for switch_ingress_port in switch_item['ingress_port']:
                print(switch_ingress_port)
                if "HGE" in switch_ingress_port:
                    config_commands = [ #配置PFC
                    'interface ' + switch_ingress_port,
                    'priority-flow-control dot1p X ingress-buffer dynamic value',
                    'priority-flow-control dot1p X headroom value',
                    'qos wred apply XXX',
                    ]
                if "WGE" in switch_ingress_port:
                    config_commands = [ #配置PFC
                    'interface ' + switch_ingress_port,
                    'priority-flow-control dot1p X ingress-buffer dynamic value',
                    'priority-flow-control dot1p X headroom value',
                    'qos wred apply XXX',
                    ]
                output = connect.send_config_set(config_commands)
            for switch_egress_port in switch_item['egress_port']:
                print(switch_egress_port)
                if "HGE" in switch_egress_port:
                    config_commands = [ #配置PFC
                    'interface ' + switch_egress_port,
                    'priority-flow-control dot1p X ingress-buffer dynamic value',
                    'priority-flow-control dot1p X headroom value',
                    'qos wred apply XXX',
                    ]
                if "WGE" in switch_egress_port:
                    config_commands = [ #配置PFC
                    'interface ' + switch_egress_port,
                    'priority-flow-control dot1p X ingress-buffer dynamic value',
                    'priority-flow-control dot1p X headroom value',
                    'qos wred apply XXX',
                    ]
                output = connect.send_config_set(config_commands)
            print('  【配置信息】交换机[' + switch_item["switch_ip"] +']已恢复默认水线配置')
            print('   -----------------------------------------------')

#给指定交换机的指定接口配置水线
def set_new_watermark_for_bytetuning(switch_ip,switch_vendor,switch_port,headroom,alpha,ecn_lowlimit,ecn_highlimit,ecn_probility):
    switch_ssh['ip'] = switch_ip
    switch_ssh['device_type'] = switch_device_type(switch_item["vendor_name"])
    connect = ConnectHandler(**switch_ssh)
    print('  【系统信息】成功连接到交换机[' + switch_ip + ']')
    output = connect.send_command('system view')
    if switch_vendor == "H3C":
            config_commands = [ #配置ECN
                'qos wred queue table ' + switch_port,
                'queue X drop-level X low-limit ' + str(ecn_lowlimit) + ' high-limit ' + str(ecn_highlimit) + ' discard-probability ' + str(ecn_probility),
                'queue X drop-level X low-limit ' + str(ecn_lowlimit) + ' high-limit ' + str(ecn_highlimit) + ' discard-probability ' + str(ecn_probility),
                'queue X drop-level X low-limit ' + str(ecn_lowlimit) + ' high-limit ' + str(ecn_highlimit) + ' discard-probability ' + str(ecn_probility),
                'queue X weighting-constant 0'
                'queue X ecn'
                'interface ' + switch_port,
                'qos wred apply ' + switch_port,
                'priority-flow-control dot1p X ingress-buffer dynamic ' + str(alpha),
                'priority-flow-control dot1p X headroom ' + str(headroom),
                ]
            output = connect.send_config_set(config_commands)
            print('  【系统信息】完成交换机['+ switch_ip +']端口['+switch_port+']水线配置下发: headroom=' + str(headroom) + ', alpha=' + str(alpha) + ', ecn_lowlimit=' + str(ecn_lowlimit) + ', ecn_highlimit=' + str(ecn_highlimit) + ', ecn_probility=' + str(ecn_probility))
    connect.disconnect()

#新水线配置下发
def set_new_watermark(headroom, alpha, ecn_limit, ecn_probility):
    for switch_item in switch_information:
        switch_ssh['ip'] = switch_item["switch_ip"]
        switch_ssh['device_type'] = switch_device_type(switch_item["vendor_name"])
        connect = ConnectHandler(**switch_ssh)
        print('  【系统信息】成功连接到交换机[' + switch_item["switch_ip"] + ']')
        output = connect.send_command('system view')
        config_commands = [ #配置ECN
            'qos wred queue table XXX',
            'queue X drop-level 0 low-limit ' + str(ecn_limit) + ' high-limit ' + str(int(ecn_limit)+value) + ' discard-probability ' + str(ecn_probility),
            'queue X drop-level 1 low-limit ' + str(ecn_limit) + ' high-limit ' + str(int(ecn_limit)+value) + ' discard-probability ' + str(ecn_probility),
            'queue X drop-level 2 low-limit ' + str(ecn_limit) + ' high-limit ' + str(int(ecn_limit)+value) + ' discard-probability ' + str(ecn_probility),
            'qos wred queue table bytedance',
            'queue X drop-level 0 low-limit ' + str(ecn_limit) + ' high-limit ' + str(int(ecn_limit)+value) + ' discard-probability ' + str(ecn_probility),
            'queue X drop-level 1 low-limit ' + str(ecn_limit) + ' high-limit ' + str(int(ecn_limit)+value) + ' discard-probability ' + str(ecn_probility),
            'queue X drop-level 2 low-limit ' + str(ecn_limit) + ' high-limit ' + str(int(ecn_limit)+value) + ' discard-probability ' + str(ecn_probility),
            ]
        output = connect.send_config_set(config_commands)
        for switch_ingress_port in switch_item['ingress_port']:
            config_commands = [ #配置PFC
                'interface ' + switch_ingress_port,
                'priority-flow-control dot1p X ingress-buffer dynamic ' + str(alpha),
                'priority-flow-control dot1p X headroom ' + str(headroom),
                ]
            output = connect.send_config_set(config_commands)
        print('  【系统信息】完成交换机['+ switch_item["switch_ip"] +']水线配置下发: headroom=' + str(headroom) + ', alpha=' + str(alpha) + ', ecn_limit=' + str(ecn_limit) + ', ecn_probility=' + str(ecn_probility))

# 查询交换机出口统计信息，返回队列信息
def get_all_switch_egress_queue():
    #脱敏处理
    return all_switch_egress_queue #返回交换机所有出口的平均队列长度

 

# 查询交换机入口统计信息，返回交换机所有入口的平均队列
def get_all_switch_ingress_queue():
    #脱敏处理
    return all_switch_ingress_queue #返回交换机所有入口的平均队列长度


# 返回交换机所有出口的平均吞吐
def get_all_switch_egress_throughput():
    #脱敏处理
    return all_switch_egerss_throughput #返回交换机所有出口的平均吞吐



#查询交换机入口统计信息，返回吞吐信息
def get_switch_in_throughput():
    #脱敏处理
    return switch_average_in_throughput

def search_best_watermark():
    global iteration
    tuning_result_filename = tuning_result_file_path + "/bytetuning_result_every_iteration.csv"
    if os.path.exists(tuning_result_filename):  #清理旧调优结果
        os.remove(tuning_result_filename)  
        with open(tuning_result_filename,'w') as csvfile:
            writer = csv.writer(csvfile, delimiter=' ')
            writer.writerow(['iteration','headroom','alpha', 'ecn_limit', 'ecn_probility','switch_throughput_every_epoch','switch_in_queue_every_epoch_1', 'switch_in_queue_every_epoch_2', 'switch_out_queue_every_epoch'])    #逻辑开始
    print('  【系统信息】当前调优策略为：遍历搜索')
    for headroom in range(1, max_Leaf_pfc_headroom, 100):
        for alpha in range(1, max_ingress_pfc_alpha, 5):
            for ecn_limit in range(1, max_Leaf_ecn_highlimit, 500):
                for ecn_probility in range(1, max_ecn_probility, 5):
                    iteration += 1
                    print('   -----------------------------------------------') 
                    print('  【系统信息】当前进行到第' + str(iteration) + '轮')
                    set_new_watermark(headroom, alpha, ecn_limit, ecn_probility)#下发水线
                    time.sleep(70*telemetry_duration) #等待若干秒再查询交换机metrics，因为metrics更新较慢
                    try:
                        switch_throughput_every_epoch = get_all_switch_egress_throughput() #收集吞吐
                    except:
                        switch_throughput_every_epoch = np.nan
                    try:
                        switch_in_queue_every_epoch = get_all_switch_ingress_queue() #收集入口队列
                    except:
                        switch_in_queue_every_epoch = np.nan
                    try:
                        switch_out_queue_every_epoch = get_all_switch_egress_queue() #收集出口队列
                    except:
                        switch_out_queue_every_epoch = np.nan
                    with open(tuning_result_filename,'a') as csvfile:
                        writer = csv.writer(csvfile, delimiter=' ')
                        writer.writerow([str(iteration), headroom, alpha, ecn_limit, ecn_probility, switch_throughput_every_epoch, switch_in_queue_every_epoch, switch_out_queue_every_epoch])

if __name__ == "__main__":
    start_print_logo()
    print("  【系统信息】读取调优配置文件：" + tuning_config_filename)
    start_save_all_switch_configuration()
    print('   -----------------------------------------------')

 
    if tuning_recovery_flag == 1:
        set_default_watermark() #恢复默认水线配置
        print(done)
    else:
        if tuning_mode == 0: #遍历搜索
            search_best_watermark()
        if tuning_mode == 1: #集中调优
            for switch_item in switch_information:
                switch_ssh['ip'] = switch_item["switch_ip"]
                switch_ssh['device_type'] = switch_device_type(switch_item["vendor_name"])
                if switch_ssh['ip'] == '10.32.124.82':
                    connect82 = ConnectHandler(**switch_ssh)
                    output = connect82.send_command('system view')
                    print('  【系统信息】成功连接到交换机[' + switch_item["switch_ip"] + ']')
                if switch_ssh['ip'] == '10.32.124.83':
                    connect83 = ConnectHandler(**switch_ssh)
                    output = connect83.send_command('system view')
                    print('  【系统信息】成功连接到交换机[' + switch_item["switch_ip"] + ']')
            bytetuning_best_watermark()
 
<img src="./bytetuning_logo.png" width = "200"/>

# ByteTuning: A centralized RoCEv2 ECN/PFC watermark tuning algorithm


## Backgroud:

RDMA over Converged Ethernet v2 (RoCEv2) is one of the most important and effective solutions for high-speed datacenter networking. Watermark is the general term for various trigger and release thresholds of RoCEv2 flow control protocols, and its reasonable configuration is an important factor affecting RoCEv2 performance. 

In this project, we report the details of our watermark tuning system ByteTuning, which has been applied in multiple data centers of ByteDance, supporting one of the largest machine learning clusters in the world. First, three real cases of network performance degradation caused by improper watermark configuration are reported, and the network performance results of different watermark configurations in three typical scenarios are traversed, indicating the necessity of watermark tuning. Then, based on the RDMA Fluid model, the influence of watermark on the RoCEv2 performance is modeled and evaluated. Next, the design of the ByteTuning is introduced, which includes three key mechanisms. Finally, We validate the performance of ByteTuning in multiple real datacenter networking environments, and the results show that ByteTuning outperforms existing solutions.

Attention: We have deleted some sensitive and confidential code, and only disclosed the ByteTuning framework and core algorithm, and some input and output needs to be configured according to your actual network environment.

## Environmental Dependence: 

Python>=3.6, netmiko

## File Directory Description:

--bytetuning.py: main program

--config: Configure Directory

&ensp; --config.yaml: Configure

--result

&ensp; --bytetuning_result_every_iteration.csv

&ensp; --...

If you have any questions, please contact tanlzh@sdas.org

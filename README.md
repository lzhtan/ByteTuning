 
<img src="./bytetuning_logo.png" width = "200"/>

# ByteTuning: A centralized RoCEv2 ECN/PFC watermark tuning algorithm


## Backgroud:

RDMA over Converged Ethernet v2 (RoCEv2) is one of the most important and effective solutions for high-speed datacenter networking. Watermark is the general term for various trigger and release thresholds of RoCEv2 flow control protocols, and its reasonable configuration is an important factor affecting RoCEv2 performance. 

In this project, we have open-sourced the framework for centralized watermark tuning.

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

For more details, please refer to our paper [ByteTuning: Watermark Tuning for RoCEv2](https://ieeexplore.ieee.org/document/10820527). 

If you have any questions, please contact tanlzh@sdas.org

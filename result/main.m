clear all;
close all;

result = xlsread('bytetuning_throughput_every_time_result.xlsx')
Iteration = result(:,1)
Throughput = result(:,2)

subplot(2,1,1);
plot(Iteration, Throughput, 'LineWidth',2)
hold on
axis([min(Iteration) max(Iteration) min(0.999*[Throughput]) max(1.001*[Throughput])])
xlabel('Iteration')
ylabel('Throughput (Gbps)')
legend('ByteTuning','Experience-based Watermark')
set(gca,'FontName','Times New Roman','FontSize',15,'LineWidth',1.5);


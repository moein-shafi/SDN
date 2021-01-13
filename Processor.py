import csv
from collections import defaultdict
import matplotlib.pyplot as plt
import numpy as np

class NodeToNode:
    def __init__(self, this_node):
        self.this_node = this_node
        self.other_nodes_time = defaultdict(list)

    def add_new_node(self, node_id, time):
        self.other_nodes_time[node_id].append(time)



def read_csv(file_name):
    result = []
    with open(file_name) as csv_file:
        csv_reader = csv.reader(csv_file)
        result = list(csv_reader)
        return result

        # line_count = 0
        # for row in csv_reader:
        #     print(f'\tSwitch number: {row[0]}, Time:{row[1]}.')
        #     line_count += 1
        # print(f'Processed {line_count} lines.')

def create_2nd_chart(x_axis: list, y_axis: list, chart_label: str,
                    x_lable: str, y_lable: str, title: str):
    plt.plot(x_axis, y_axis, label=chart_label)

    plt.xlabel(x_lable)
    plt.ylabel(y_lable)
    # plt.xticks(np.arange(min(x_axis), max(x_axis) + 1, x_ticks))
    # plt.yticks(np.arange(min(y_axis), max(y_axis) + 1, y_ticks))
    plt.title(title)
        
def draw_switch_update_time_diagram():
    switch_update_time_list = read_csv("switch_flow_table_update_times.txt")
    switch_update_time_dict = defaultdict(list)
    for row in switch_update_time_list:
        switch_update_time_dict[int(row[0])].append(float(row[1]))

    for switch, update_time in switch_update_time_dict.items():
        create_2nd_chart(update_time, range(len(update_time)), f"switch {switch}",
                        "Update Time", "Count", "Switchs flow table update time")
    plt.legend()
    plt.show()

def draw_node_to_node_delivery_time():
    node_to_node_time_list = read_csv("node-to-node.txt")
    node_to_node_time_dict = defaultdict(NodeToNode)

    for row in node_to_node_time_list:
        if row[0] not in node_to_node_time_dict.keys():
            node_to_node_time_dict[row[0]] = NodeToNode(row[0])
        node_to_node_time_dict[row[0]].other_nodes_time[row[1]].append(float(row[2]))

    for src, node_to_nodes in node_to_node_time_dict.items():
        for dst, times in node_to_nodes.other_nodes_time.items():
            create_2nd_chart(times, range(len(times)), dst,
                        "Time", "Count", f"From src {src}")
        plt.legend()
        plt.show()



if __name__ == '__main__':
    draw_switch_update_time_diagram()
    draw_node_to_node_delivery_time()

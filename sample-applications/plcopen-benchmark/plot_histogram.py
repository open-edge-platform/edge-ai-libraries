#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
# Copyright (C) 2025 Intel Corporation

import argparse

import matplotlib
import matplotlib.pyplot as plt
import numpy as np

parser = argparse.ArgumentParser()
parser.add_argument("--logfiles", nargs='*', help="Directory path of the log file.",
                    type=str)
parser.add_argument("--start", nargs='?', help="Start cycle.",
                    type=int, default=0)
parser.add_argument("--end", nargs='?', help="End cycle.",
                    type=int, default=0)
parser.add_argument("--lat", action='store_true', help="Latency statistics.")                    
parser.add_argument("--dcm", action='store_true', help="DCM statistics.")
parser.add_argument("--cac", action='store_true', help="Cache statistics.")
parser.add_argument("--exe", action='store_true', help="Execution time statistics.")
parser.add_argument("--ins", action='store_true', help="Instruction count statistics.")                 

def main():
  args = parser.parse_args()
  print("Loading logfiles...: {}".format(args.logfiles))
  n_bins = 20

  x_list = []
  t_list = []
  if (len(args.logfiles) > 0):
    for logfile in args.logfiles:
      if (logfile != ""):
        x = []
        t = []
        count = 0
        with open(logfile) as fp:
          for line in fp:
            count += 1
            x.append(count/1000.0)
            t.append(int(line.strip()))

        x_list.append(x)
        t_list.append(t)

        #for i in range(0, len(x)):
        #  print("Time {}: {}".format(x[i], t[i]))
  print("Loaded {} files.".format(len(args.logfiles)))
  
  # Latency data processing
  if (args.lat):
    print("Processing latency data...")
    x = []
    t = []
    if len(x_list) == 0 or len(t_list) == 0:
      print("Warning: Empty data.")
      return

    if len(x_list[0]) == 0 or len(t_list[0]) == 0:
      print("Warning: Empty data.")
      return

    x = x_list[0].copy()
    t = t_list[0].copy()

    if (args.start >= len(x)):
      print("Warning: start cycle {} exceeds max lenth {}.".format(args.start, len(x_list[0])))
      return
    
    x = x[args.start:-1]
    t = t[args.start:-1]

    fig, ax = plt.subplots()
    ax.hist(t, bins=n_bins, label="Latency")

    ax.set(xlabel='time (ns)', ylabel='count',
          title='Benchmark Test')
    ax.grid()
    handles, labels = ax.get_legend_handles_labels()
    ax.legend(handles, labels)

    fig.set_tight_layout(True)
    fig.savefig("lat-histogram.png")

  # Cache data processing
  if (args.lat):
    print("Processing cache data...")
    x = []
    t = []
    if len(x_list) == 0 or len(t_list) == 0:
      print("Warning: Empty data.")
      return

    if len(x_list[0]) == 0 or len(t_list[0]) == 0:
      print("Warning: Empty data.")
      return

    x = x_list[0].copy()
    t = t_list[0].copy()

    if (args.start >= len(x)):
      print("Warning: start cycle {} exceeds max lenth {}.".format(args.start, len(x_list[0])))
      return
    
    x = x[args.start:-1]
    t = t[args.start:-1]

    fig, ax = plt.subplots()
    ax.hist(t, bins=n_bins, label="Cache")

    ax.set(xlabel='Cache Miss', ylabel='count',
          title='Benchmark Test')
    ax.grid()
    handles, labels = ax.get_legend_handles_labels()
    ax.legend(handles, labels)

    fig.set_tight_layout(True)
    fig.savefig("cac-histogram.png")

  # DCM data processing
  if (args.dcm):
    print("Processing dcm data...")
    x = []
    t = []
    if len(x_list) == 0 or len(t_list) == 0:
      print("Warning: Empty data.")
      return

    if len(x_list[0]) == 0 or len(t_list[0]) == 0:
      print("Warning: Empty data.")
      return

    x = x_list[0].copy()
    t = t_list[0].copy()

    if (args.start >= len(x)):
      print("Warning: start cycle {} exceeds max lenth {}.".format(args.start, len(x_list[0])))
      return
    
    x = x[args.start:-1]
    t = t[args.start:-1]

    index = 0
    for i in range(len(t)):
      # Start statistics from the cycle when DCM < 10us
      if t[i] >= 10000: 
        index = i + 1
    
    print("DCM start from cycle {}".format(index + args.start))
    
    x = x[index:-1]
    t = t[index:-1]

    fig, ax = plt.subplots()
    ax.hist(t, bins=n_bins, label="DCM")

    ax.set(xlabel='time (ns)', ylabel='count',
          title='Benchmark Test')
    ax.grid()
    handles, labels = ax.get_legend_handles_labels()
    ax.legend(handles, labels)

    fig.set_tight_layout(True)
    fig.savefig("dcm-histogram.png")

  # Execution time data processing  
  if (args.exe):
    print("Processing execution time data...")

    if len(x_list) < 3 or len(t_list) < 3:
      print("Warning: not enough logfiles, need 3 logfiles.")
      return

    if len(x_list[0]) == 0 or len(x_list[1]) == 0 or len(x_list[2]) == 0:
      print("Warning: empty data in one log file.")
      return

    if len(x_list[0]) != len(x_list[1]) or len(x_list[0]) != len(x_list[2]):
      print("Warning: length of three logs not the same.")
      return

    x = x_list[0].copy()
    t = [0] * len(x_list[0])
    for i in range(len(x_list[0])):
      t[i] = t_list[0][i] + t_list[1][i] + t_list[2][i]

    if (args.start >= len(x)):
      print("Warning: start cycle {} exceeds max lenth {}.".format(args.start, len(x_list[0])))
      return
    
    x = x[args.start:-1]
    t = t[args.start:-1]

    fig, ax = plt.subplots()
    ax.hist(t, bins=n_bins, label="Execution Time")

    ax.set(xlabel='time (ns)', ylabel='count',
          title='Benchmark Test')
    ax.grid()
    handles, labels = ax.get_legend_handles_labels()
    ax.legend(handles, labels)

    fig.set_tight_layout(True)
    fig.savefig("exe-histogram.png")

  # Instruction count data processing
  if (args.ins):
    print("Processing instruction count data...")
    x = []
    t = []
    if len(x_list) == 0 or len(t_list) == 0:
      print("Warning: Empty data.")
      return

    if len(x_list[0]) == 0 or len(t_list[0]) == 0:
      print("Warning: Empty data.")
      return

    x = x_list[0].copy()
    t = t_list[0].copy()

    if (args.start >= len(x)):
      print("Warning: start cycle {} exceeds max lenth {}.".format(args.start, len(x_list[0])))
      return
    
    x = x[args.start:-1]
    t = t[args.start:-1]

    fig, ax = plt.subplots()
    ax.hist(t, bins=n_bins, label="Instruction Count")

    ax.set(xlabel='instruction', ylabel='count',
          title='Benchmark Test')
    ax.grid()
    handles, labels = ax.get_legend_handles_labels()
    ax.legend(handles, labels)

    fig.set_tight_layout(True)
    fig.savefig("ins-histogram.png")

if __name__ == "__main__":
    main()

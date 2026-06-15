#!/usr/bin/env python3

import json
import os
import subprocess
import argparse
import re
import signal
import sys

from statistics import mean, stdev

SCRIPT_DIR = os.path.dirname(os.path.realpath(__file__))
PKTGEN_DIR = f"{SCRIPT_DIR}/../build/dpdk-burst-replay"

PKTGEN_SCRIPT_THROUGHPUT = f"{PKTGEN_DIR}/src/config.yaml"
PKTGEN_RESULTS_SND_PORT         = f"{PKTGEN_DIR}/results_snd_port.csv"
PKTGEN_RESULTS_RCV_PORT         = f"{PKTGEN_DIR}/results_rcv_port.csv"
RESULTS_FILENAME         = "results.csv"

MIN_RATE             = 0   # Gbps
MAX_RATE             = 100 # Gbps
LOSS_THRESHOLD       = 0.4 # %
CHECKING_ERROR       = 0.1 # relative error

DEFAULT_TX_CORES            = 2
DEFAULT_RX_CORES            = 2
DEFAULT_DURATION_SEC        = 10 # seconds
DEFAULT_ITERATIONS          = 10
DEFAULT_WARMUP_DURATION_SEC = 3 # seconds

Billion = 1_000_000_000
Million = 1_000_000
MAX_NIC_THROUHGPUT_BPS = 100 * Billion # 100 Gbps

DPDK_BURST_REPLAY_CONFIG_TEMPLATE = \
"""
---
traces: 
  - path: "{{pcap}}"
    tx_queues: 8
  - path: "{{pcap}}"
    tx_queues: 8
  - path: "{{pcap}}"
    tx_queues: 8
  - path: "{{pcap}}"
    tx_queues: 8
  - path: "{{pcap}}"
    tx_queues: 8
numacore: {{numacore}}
nbruns: -1
timeout: {{duration}}
max_mpps: -1
max_mbps: {{rate}}
write_csv: True
wait_enter: False
slow_mode: False
convert_to_json: True
use_mac_filter: False
enable_jumbo: False
nb_rx_queues: 16
nb_rx_cores: 4
stats:
{{stats}}
send_port_pci: {{sendport}}
enable_rest_server: False
rest_server_port: 5000
loglevel: TRACE
"""

DPDK_BURST_REPLAY_CONFIG_TEMPLATE_SCR = \
"""
---
traces: 
  - path: "{{pcap}}"
    tx_queues: 8
  - path: "{{pcap}}"
    tx_queues: 8
  - path: "{{pcap}}"
    tx_queues: 8
  - path: "{{pcap}}"
    tx_queues: 8
  - path: "{{pcap}}"
    tx_queues: 8
numacore: {{numacore}}
nbruns: -1
timeout: {{duration}}
max_mpps: -1
max_mbps: {{rate}}
write_csv: True
wait_enter: False
slow_mode: False
convert_to_json: True
use_mac_filter: True
enable_jumbo: False
nb_rx_queues: {{num_rx_queues}}
nb_rx_cores: 4
stats:
{{stats}}
send_port_pci: {{sendport}}
enable_rest_server: False
rest_server_port: 5000
loglevel: TRACE
"""

def kill_pktgen(sig, frame):
    print("[*] Killing DPDK burst replay instances", flush=True)
    os.system("sudo killall -9 dpdk-replay")
    sys.exit(0)

def build_script_throughput(pcap, rate, cfg, duration_sec, warmup_duration_sec=DEFAULT_WARMUP_DURATION_SEC, scr=False, num_rx_queues=8):
    if scr:
        script = DPDK_BURST_REPLAY_CONFIG_TEMPLATE_SCR
        script = script.replace('{{num_rx_queues}}', str(num_rx_queues))
    else:
        script = DPDK_BURST_REPLAY_CONFIG_TEMPLATE

    script = script.replace('{{pcap}}', str(pcap))
    script = script.replace('{{sendport}}', str(cfg['tx']['dev']))
    script = script.replace('{{recvport}}', str(cfg['rx']['dev']))
    script = script.replace('{{rate}}', str(rate))
    script = script.replace('{{duration}}', str(duration_sec + warmup_duration_sec))
    script = script.replace('{{results_snd_port}}', PKTGEN_RESULTS_SND_PORT)
    script = script.replace('{{results_rcv_port}}', PKTGEN_RESULTS_RCV_PORT)

    stats = [
        f'  - pci_id: {cfg["tx"]["dev"]}',
        f'    file_name: "{PKTGEN_RESULTS_SND_PORT}"',
    ]
    if cfg['tx']['dev'] != cfg['rx']['dev']:
        stats.extend([
            f'  - pci_id: {cfg["rx"]["dev"]}',
            f'    file_name: "{PKTGEN_RESULTS_RCV_PORT}"',
        ])
    script = script.replace('{{stats}}', '\n'.join(stats))

    # script = script.replace('{{n_to_send}}', str(n_to_send))

    numa = get_device_numa_node(cfg['tx']['dev'])
    script = script.replace('{{numacore}}', str(numa))
    
    f = open(PKTGEN_SCRIPT_THROUGHPUT, 'w')
    f.write(script)
    f.close()

def validate_pcie_dev(pcie_dev):
    cmd  = [ "lspci", "-mm" ]
    info = subprocess.check_output(cmd, stderr=subprocess.DEVNULL)
    info = info.decode('utf-8')
    info = info.split('\n')

    for line in info:
        line   = line.split(' ')
        device = line[0]

        if device in pcie_dev:
            return
    
    print(f'Invalid PCIE dev \"{pcie_dev}\"')
    exit(1)

def get_device_numa_node(pcie_dev):
    try:
        cmd  = [ "lspci", "-s", pcie_dev, "-vv" ]
        info = subprocess.check_output(cmd, stderr=subprocess.DEVNULL)
        info = info.decode('utf-8')
        result = re.search(r"NUMA node: (\d+)", info)
        
        if not result:
            return 0

        assert result
        return int(result.group(1))
    except subprocess.CalledProcessError:
        print(f'Invalid PCIE dev \"{pcie_dev}\"')
        exit(1)

def get_all_cpus():
    cmd    = [ "lscpu" ]
    info   = subprocess.check_output(cmd, stderr=subprocess.DEVNULL)
    info   = info.decode('utf-8')
    result = re.search(r"CPU\(s\):\D+(\d+)", info)

    assert result
    total_cpus = int(result.group(1))
    
    return [ x for x in range(total_cpus) ]

def get_numa_node_cpus(node):
    cmd  = [ "lscpu" ]
    info = subprocess.check_output(cmd, stderr=subprocess.DEVNULL)
    info = info.decode('utf-8')
    info = [ line for line in info.split('\n') if 'NUMA' in line ]

    assert len(info) > 0
    total_nodes_match = re.search(r"\D+(\d+)", info[0])
    
    assert total_nodes_match
    total_nodes = int(total_nodes_match.group(1))

    if node > total_nodes:
        print(f'Requested NUMA node ({node}) >= available nodes ({total_nodes})')
        exit(1)
    
    if total_nodes == 1:
        return get_all_cpus()

    assert len(info) == total_nodes + 1
    node_info = info[node + 1]

    if '-' in node_info:
        cpus_match = re.search(r"\D+(\d+)\-(\d+)$", node_info)
        assert cpus_match

        min_cpu = int(cpus_match.group(1))
        max_cpu = int(cpus_match.group(2))

        return [ cpu for cpu in range(min_cpu, max_cpu + 1) ]

    cpus_match = re.search(r"\D+([\d,]+)$", node_info)
    assert cpus_match
    return [ int(i) for i in cpus_match.groups(0)[0].split(',') ]

def get_pcie_dev_cpus(pcie_dev):
    numa = get_device_numa_node(pcie_dev)
    cpus = get_numa_node_cpus(numa)
    print(f'[*] PCIe={pcie_dev} NUMA={numa} CPUs={cpus}')
    return cpus

def get_port_from_pcie_dev(pcie_dev):
    # I'm not sure this is the convention, but it works so far
    return int(pcie_dev.split('.')[1])

def build_pktgen_command(script):
    cmd = [
        "sudo",
        f"{PKTGEN_DIR}/build/src/dpdk-replay",
        "--config", f"{script}",
    ]

    print(f'[*] DPDK replay command: {" ".join(cmd)}')
    
    return cmd

def save_throughput_data(data):
    results = []

    results.append(str(data['tx']['pkt_rate']))
    results.append(str(data['tx']['rate']))
    results.append(str(data['rx']['pkt_rate']))
    results.append(str(data['rx']['rate']))
    results.append(str(data['loss']))

    with open(RESULTS_FILENAME, 'w') as f:
        f.write('# tx (Mpps), tx (Gbps), rx (Mpps), rx (Gbps), loss (%)')
        f.write('\n')
        f.write(','.join(results))
        f.write('\n')

def save_latency_data(data):
    with open(RESULTS_FILENAME, 'w') as f:
        for d in data:
            f.write(f'{d}\n')

def run_pktgen(pcap, rate, cfg, duration_sec, lb=False, dry_run=False, verbose=False, scr=False, num_rx_queues=8):
    def __run(dry_run, pktgen_cmd):
        if dry_run:
            exit(0)

        if verbose:
            return subprocess.run(pktgen_cmd, cwd=PKTGEN_DIR)
        return subprocess.run(
            pktgen_cmd,
            cwd=PKTGEN_DIR,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL
        )

    if lb:
        print(f"[*] Registering backend")
        print(f"[*] No support for LB yet")
        exit(1)
        assert proc.returncode == 0

    
    print(f"[*] Replaying at {rate}% linerate")
    # The rate is in 0-100%, I want to convert it to Gbps
    rate_bps = (rate / 100) * MAX_NIC_THROUHGPUT_BPS
    # Now let's convert it to Mbps
    rate_mbps = int(rate_bps / Million)

    print(f"[*] Replaing at {rate_mbps} Mbps")


    build_script_throughput(pcap, rate_mbps, cfg, duration_sec, scr=scr, num_rx_queues=num_rx_queues)	
    pktgen_cmd = build_pktgen_command(PKTGEN_SCRIPT_THROUGHPUT)

    if lb:
        # Swap
        print( "[*] Load Balancer mode not supported yet")
        exit(1)
        # cfg['tx']['port'], cfg['rx']['port'] = cfg['rx']['port'], cfg['tx']['port']

    proc = __run(dry_run, pktgen_cmd)
    print("[*] DPDK replay finished with code", proc.returncode)
    assert proc.returncode == 0

    results_snd_port_file = PKTGEN_RESULTS_SND_PORT.replace('.csv', '.json')
    results_rcv_port_file = PKTGEN_RESULTS_RCV_PORT.replace('.csv', '.json')

    # Load JSON data
    with open(results_snd_port_file, 'r') as file:
        snd_port_data = json.load(file)

    same_port = cfg['tx']['dev'] == cfg['rx']['dev']
    if same_port:
        rcv_port_data = snd_port_data
    else:
        with open(results_rcv_port_file, 'r') as file:
            rcv_port_data = json.load(file)

    total_rx_packets = 0
    total_rx_bytes = 0
    total_rx_rate = 0.0
    total_tx_packets = 0
    total_tx_bytes = 0
    total_tx_rate = 0.0
    num_entries_snd_data = len(snd_port_data)
    num_entries_rcv_data = len(rcv_port_data)

    # assert num_entries_snd_data == num_entries_rcv_data
    # assert num_entries_snd_data == duration_sec + DEFAULT_WARMUP_DURATION_SEC
    # assert num_entries_rcv_data == duration_sec + DEFAULT_WARMUP_DURATION_SEC

    os.remove(PKTGEN_RESULTS_SND_PORT)
    os.remove(results_snd_port_file)
    if not same_port:
        os.remove(PKTGEN_RESULTS_RCV_PORT)
        os.remove(results_rcv_port_file)

    for entry in snd_port_data[DEFAULT_WARMUP_DURATION_SEC:]:
        total_tx_packets += int(entry['TX-packets'])
        total_tx_bytes += int(entry['TX-bytes'])
        total_tx_rate += float(entry['TX-rate'])

    average_tx_packets = total_tx_packets / (num_entries_snd_data-DEFAULT_WARMUP_DURATION_SEC)
    average_tx_rate = total_tx_rate / (num_entries_snd_data-DEFAULT_WARMUP_DURATION_SEC)

    for entry in rcv_port_data[DEFAULT_WARMUP_DURATION_SEC:]:
        total_rx_packets += int(entry['RX-packets'])
        total_rx_bytes += int(entry['RX-bytes'])
        total_rx_rate += float(entry['RX-rate'])
    
    average_rx_packets = total_rx_packets / (num_entries_rcv_data-DEFAULT_WARMUP_DURATION_SEC)
    average_rx_rate = total_rx_rate / (num_entries_rcv_data-DEFAULT_WARMUP_DURATION_SEC)

    if average_tx_packets == 0:
        print(f'[*][!] No packets sent')
        exit(1)
        
    pkt_loss = (average_tx_packets - average_rx_packets) / average_tx_packets
    # pkt_loss = (average_tx_rate - average_rx_rate) / average_tx_rate

    data = {
        'tx': {
            'rate':     float(average_tx_rate),
            'pkt_rate': float(average_tx_packets) / Million,
        },
        'rx': {
            'rate':     float(average_rx_rate),
            'pkt_rate': float(average_rx_packets) / Million,
        },
        'loss': float(pkt_loss) * 100,
    }

    print(f"[*] TX   {data['tx']['pkt_rate']:3.2f} Mpps {data['tx']['rate']:3.2f} Gbps")
    print(f"[*] RX   {data['rx']['pkt_rate']:3.2f} Mpps {data['rx']['rate']:3.2f} Gbps")
    print(f"[*] loss {data['loss']:3.2f}%")

    return data

def get_cfg(tx_pcie_dev, rx_pcie_dev, num_tx_cores, num_rx_cores):
    all_cores     = get_all_cpus()
    # Remove number 0 from the list of cores
    for core in all_cores:
        if core == 0:
            all_cores.remove(core)

    all_tx_cores  = get_pcie_dev_cpus(tx_pcie_dev)
    all_rx_cores  = get_pcie_dev_cpus(rx_pcie_dev)

    master_core   = [0]
    tx_cores      = select_cores(all_tx_cores, num_tx_cores + 1, master_core)
    rx_cores      = select_cores(all_tx_cores, num_rx_cores + 1, master_core + tx_cores)
    
    tx_rx_cores = [ tx_cores[0] ]
    tx_tx_cores = tx_cores[1:]

    rx_rx_cores = rx_cores[1:]
    rx_tx_cores = [ rx_cores[0] ]

    tx_port  = get_port_from_pcie_dev(tx_pcie_dev)
    rx_port  = get_port_from_pcie_dev(rx_pcie_dev)

    print(f'[*] TX dev={tx_pcie_dev} port={tx_port} cores={tx_tx_cores}')
    print(f'[*] RX dev={rx_pcie_dev} port={rx_port} cores={rx_rx_cores}')
    print(f'[*] Master core={master_core}')

    cfg = {
        'tx': {
            'dev':   tx_pcie_dev,
            'port':  tx_port,
            'cores': {
                'tx': tx_tx_cores,
                'rx': tx_rx_cores,
            },
        },
        'rx': {
            'dev':   rx_pcie_dev,
            'port':  rx_port,
            'cores': {
                'tx': rx_tx_cores,
                'rx': rx_rx_cores,
            },
        },
        'master': master_core
    }

    return cfg

def search_throughput_fast(pcap, cfg, duration_sec, iterations, lb=False, dry_run=False, verbose=False, scr=False, num_rx_queues=8, start_rate=100.0):
    upper_bound = 100.0  # %
    lower_bound = 0      # %

    max_rate = upper_bound
    mid_rate = float(start_rate)
    min_rate = lower_bound

    best_data = {
        'tx': {
            'rate':     0,
            'pkt_rate': 0,
        },
        'rx': {
            'rate':     0,
            'pkt_rate': 0,
        },
        'loss': 0,
    }

    last_tx_rate = -1
    last_requested_tx_rate = -1
    i = 0
    repeated_run = False
    best_rx_rate = -1
    lower_factor = 0.8  # Default starting factor
    upper_factor = 1.2  # Default starting factor

    while True:
        rate = mid_rate

        if rate < 0.1 or i >= iterations:
            break

        data = run_pktgen(pcap, rate, cfg, duration_sec, lb=lb, dry_run=dry_run, verbose=verbose, scr=scr, num_rx_queues=num_rx_queues)
        observed_rx_rate = data["rx"]["rate"]

        # Very few packets sent, something went wrong
        if data["tx"]["rate"] < 0.1:
            print(f'[*][!] Too few packets sent, repeating run')
            continue

        # Invalid run check
        invalid_run = (
            rate > last_requested_tx_rate and data["tx"]["rate"] < last_tx_rate  # TX rate decreases unexpectedly
        ) or (
            rate < 50 and abs((rate / last_requested_tx_rate) - (data["tx"]["rate"] / last_tx_rate)) > CHECKING_ERROR  # Inconsistency at low rates
        )

        if last_tx_rate > 0 and invalid_run:
            if repeated_run:
                print(f'[*][!] Weird data, but we keep going...')
            else:
                print(f'[*][!] Weird data, repeating run')
                repeated_run = True
                continue

        repeated_run = False

        # Dynamically adjust factors based on loss and RX behavior
        loss = data['loss']
        if loss < LOSS_THRESHOLD:
            # Expand search upwards if loss is low
            upper_factor = min(upper_factor * 1.1, 2.0)  # Cap at 200%
            lower_factor = max(lower_factor * 0.9, 0.5)  # Floor at 50%
        else:
            # Narrow search if loss is high
            upper_factor = max(upper_factor * 0.9, 1.0)  # Floor at 100%
            lower_factor = min(lower_factor * 1.1, 1.0)  # Cap at 100%

        # Update bounds based on adjusted factors
        lower_bound = max(0.1, observed_rx_rate * lower_factor)
        upper_bound = min(100.0, observed_rx_rate * upper_factor)
        mid_rate = (lower_bound + upper_bound) / 2

        print(f"[*] Updated search range: lower={lower_bound:.2f}%, upper={upper_bound:.2f}%, mid={mid_rate:.2f}%")

        # Update best result if loss is below threshold
        if loss < LOSS_THRESHOLD and data["rx"]["rate"] > best_rx_rate:
            best_data = data
            best_rx_rate = data["rx"]["rate"]

        # Terminate if converged or out of iterations
        if mid_rate == upper_bound or i + 1 >= iterations:
            break

        i += 1
        last_tx_rate = data["tx"]["rate"]
        last_requested_tx_rate = rate

    print()
    print("[*] Best results:")
    print(f'[*]   TX:   {best_data["tx"]["pkt_rate"]:3.2f} Mpps {best_data["tx"]["rate"]:3.2f} Gbps')
    print(f'[*]   RX:   {best_data["rx"]["pkt_rate"]:3.2f} Mpps {best_data["rx"]["rate"]:3.2f} Gbps')
    print(f'[*]   loss: {best_data["loss"]:.2f} %')

    return best_data


def search_throughput(pcap, cfg, duration_sec, iterations, lb=False, dry_run=False, verbose=False, scr=False, num_rx_queues=8, start_rate=100.0):
    upper_bound = 100.0 # %
    lower_bound = 0     # %
    
    max_rate = upper_bound
    mid_rate = float(start_rate)
    min_rate = lower_bound

    best_data = {
        'tx': {
            'rate':     0,
            'pkt_rate': 0,
        },
        'rx': {
            'rate':     0,
            'pkt_rate': 0,
        },
        'loss': 0,
    }

    last_tx_rate = -1
    last_requested_tx_rate = -1
    i = 0
    repeated_run = False
    best_rx_rate = -1
    
    while True:
        rate = mid_rate

        if rate < 0.1 or i >= iterations:
            break
        
        data = run_pktgen(pcap, rate, cfg, duration_sec, lb=lb, dry_run=dry_run, verbose=verbose, scr=scr, num_rx_queues=num_rx_queues)

        # Very few packets sent, something went wrong
        if data["tx"]["rate"] < 0.1:
            print(f'[*][!] Too few packets sent, repeating run')
            continue

        # If we are increasing the rate, pktgen should not be sending less than before
        invalid_run = (rate > last_requested_tx_rate and data["tx"]["rate"] < last_tx_rate)

        # Difference in what we asked for and what we got, compared to the previous run
        invalid_run |= rate < 50 and \
            (abs((rate/last_requested_tx_rate) - (data["tx"]["rate"] / last_tx_rate)) > CHECKING_ERROR)

        if last_tx_rate > 0 and invalid_run:
            # The check if it's a repeated run is to avoid infinite loops
            # (probably the invalid run won't repeat again)
            if repeated_run:
                print(f'[*][!] weird data, but we keep going...')
            else:
                print(f'[*][!] weird data, repeating run')
                repeated_run = True
                continue
        
        repeated_run = False

        if data['loss'] < LOSS_THRESHOLD:
            if data["rx"]["rate"] > best_rx_rate:
                best_data = data
                best_rx_rate = data["rx"]["rate"]

            if mid_rate == upper_bound or i + 1 >= iterations:
                break

            min_rate = mid_rate
            mid_rate = mid_rate + (max_rate - mid_rate) / 2
        else:
            max_rate = mid_rate
            mid_rate = min_rate + (mid_rate - min_rate) / 2
        
        i += 1
        last_tx_rate = data["tx"]["rate"]
        last_requested_tx_rate = rate

    print()
    print( "[*] Best results:")
    print(f'[*]   TX:   {best_data["tx"]["pkt_rate"]:3.2f} Mpps {best_data["tx"]["rate"]:3.2f} Gbps')
    print(f'[*]   RX:   {best_data["rx"]["pkt_rate"]:3.2f} Mpps {best_data["rx"]["rate"]:3.2f} Gbps')
    print(f'[*]   loss: {best_data["loss"]:.2f} %')

    return best_data

def select_cores(all_cores, num_cores, to_ignore):
    filtered_cores = [ core for core in all_cores if core not in to_ignore ]
    
    if len(filtered_cores) < num_cores:
        print(f'Number of requested cores {num_cores} > available cores {len(all_cores)}')
        print(f'Available cores: {all_cores}')
        print(f'Filtered cores:  {filtered_cores}')
        exit(1)
    
    return filtered_cores[:num_cores]

def range_limited_rate(arg):
    MIN_VAL = MIN_RATE
    MAX_VAL = MAX_RATE

    try:
        f = float(arg)
    except ValueError:    
        raise argparse.ArgumentTypeError("Must be a floating point number")
    if f <= MIN_VAL or f > MAX_VAL:
        raise argparse.ArgumentTypeError(f"Argument must be < {MAX_VAL} + and >= {MIN_VAL}")
    return f

def main():
    # Kill pktgen on SIGINT
    signal.signal(signal.SIGINT, kill_pktgen)

    parser = argparse.ArgumentParser()
    
    parser.add_argument('tx', type=str, help='TX PCIe device')
    parser.add_argument('rx', type=str, help='RX PCIe device')
    parser.add_argument('pcap', type=str, help='pcap to replay')

    parser.add_argument('--rate', type=range_limited_rate, default=100, help='replay rate (%% of total capacity)')

    parser.add_argument('--tx-cores',
        type=int, default=DEFAULT_TX_CORES, required=False, help='Number of TX cores')

    parser.add_argument('--rx-cores',
        type=int, default=DEFAULT_RX_CORES, required=False, help='Number of RX cores')
    
    parser.add_argument('--duration',
        type=int, default=DEFAULT_DURATION_SEC, required=False, help='Time duration (seconds)')

    parser.add_argument('--iterations',
        type=int, default=DEFAULT_ITERATIONS, required=False,
        help='Iterations for finding stable throughput')
    
    parser.add_argument('--lb',
        default=False, required=False, action='store_true',
        help='Load Balancer mode')
    
    parser.add_argument('--find-stable-throughput',
        action='store_true', required=False, help='Time duration (seconds)')

    parser.add_argument('--find-stable-throughput-fast',
        action='store_true', required=False, help='Time duration (seconds)')

    parser.add_argument('--dry-run',
        default=False, required=False, action='store_true',
        help='Dry run (does not run pktgen, just prints out the configuration)')

    parser.add_argument('--latency',
        default=False, required=False, action='store_true',
        help='Measure latency')
    
    parser.add_argument('-v',
        default=False, required=False, action='store_true',
        help='Shows Pktgen output')

    parser.add_argument('--scr',
        default=False, required=False, action='store_true',
        help='Use MAC filter')
    
    parser.add_argument('--num-rx-queues',
        type=int, default=8, required=False, help='Number of RX queues')

    parser.add_argument('--start-rate', type=range_limited_rate, default=100, help='Start rate (%% of total capacity)')

    args = parser.parse_args()

    pcap = os.path.abspath(args.pcap)
    assert os.path.exists(pcap)

    validate_pcie_dev(args.tx)
    validate_pcie_dev(args.rx)

    if args.scr:
        print(f"[*] Using MAC filter")
        print(f"[*] Using {args.num_rx_queues} RX queues")

    cfg = get_cfg(args.tx, args.rx, args.tx_cores, args.rx_cores)

    if args.latency:
        print(f"[*] The DPDK burst replay script doesn't support latency measurement yet")
        exit(1)
    else:
        if args.find_stable_throughput:
            data = search_throughput(pcap, cfg, args.duration, args.iterations, lb=args.lb, dry_run=args.dry_run, verbose=args.v, scr=args.scr, num_rx_queues=args.num_rx_queues, start_rate=args.start_rate)
        elif args.find_stable_throughput_fast:
            data = search_throughput_fast(pcap, cfg, args.duration, args.iterations, lb=args.lb, dry_run=args.dry_run, verbose=args.v, scr=args.scr, num_rx_queues=args.num_rx_queues, start_rate=args.start_rate)
        else:
            data = run_pktgen(pcap, args.rate, cfg, args.duration, lb=args.lb, dry_run=args.dry_run, verbose=args.v, scr=args.scr, num_rx_queues=args.num_rx_queues)

        save_throughput_data(data)

if __name__ == '__main__':
    main()

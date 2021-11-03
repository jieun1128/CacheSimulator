#!/usr/bin/env python

import yaml, cache, argparse, logging, pprint
from terminaltables.other_tables import UnixTable

def main():
    #Set up our arguments
    parser = argparse.ArgumentParser(description='Simulate a cache')
    parser.add_argument('-c','--config-file', help='Configuration file for the memory heirarchy', required=False, default='configs/config_simple_multilevel')
    parser.add_argument('-t', '--trace-file', help='Tracefile containing instructions', required=False, default='traces/simple.txt')
    parser.add_argument('-l', '--log-file', help='Log file name', required=False)
    parser.add_argument('-p', '--pretty', help='Use pretty colors', required=False, action='store_true')
    parser.add_argument('-d', '--draw-cache', help='Draw cache layouts', required=False, action='store_true')
    arguments = vars(parser.parse_args())
    
    if arguments['pretty']:
        import colorer

    log_filename = 'cache_simulator.log'
    if arguments['log_file']:
        log_filename = arguments['log_file']

    #Clear the log file if it exists
    with open(log_filename, 'w'):
        pass

    logger = logging.getLogger()    # 로그 출력하기 
    fh = logging.FileHandler(log_filename)
    sh = logging.StreamHandler()
    logger.addHandler(fh)
    logger.addHandler(sh)

    fh_format = logging.Formatter('%(message)s')
    fh.setFormatter(fh_format)
    sh.setFormatter(fh_format)
    logger.setLevel(logging.INFO)
    
    logger.info('Loading config...')
    config_file = open(arguments['config_file'])
    configs = yaml.load(config_file)
    hierarchy = build_hierarchy(configs, logger)
    logger.info('Memory hierarchy built.')

    logger.info('Loading tracefile...')
    trace_file = open(arguments['trace_file'])
    trace = trace_file.read().splitlines()
    trace = [item for item in trace if not item.startswith('#')]
    logger.info('Loaded tracefile ' + arguments['trace_file'])
    logger.info('Begin simulation!')
    simulate(hierarchy, trace, logger)
    if arguments['draw_cache']:
        for cache in hierarchy:
            if hierarchy[cache].next_level:
                print_cache(hierarchy[cache])

#Print the contents of a cache as a table
#If the table is too long, it will print the first few sets,
#break, and then print the last set
def print_cache(cache):
    table_size = 5
    ways = [""]
    sets = []
    set_indexes = sorted(cache.data.keys())
    if len(cache.data.keys()) > 0:
        first_key = list(cache.data.keys())[0]
        way_no = 0
        
        #Label the columns
        for way in range(cache.associativity):
            ways.append("Way " + str(way_no))
            way_no += 1
        
        #Print either all the sets if the cache is small, or just a few
        #sets and then the last set
        sets.append(ways)
        if len(set_indexes) > table_size + 4 - 1:
            for s in range(min(table_size, len(set_indexes) - 4)):
                set_ways = cache.data[set_indexes[s]].keys()
                temp_way = ["Set " + str(s)]
                for w in set_ways:
                    temp_way.append(cache.data[set_indexes[s]][w].address)
                sets.append(temp_way)
            
            for i in range(3):
                temp_way = ['.']
                for w in range(cache.associativity):
                    temp_way.append('')
                sets.append(temp_way)
            
            set_ways = cache.data[set_indexes[len(set_indexes) - 1]].keys()
            temp_way = ['Set ' + str(len(set_indexes) - 1)]
            for w in set_ways:
                temp_way.append(cache.data[set_indexes[len(set_indexes) - 1]][w].address)
            sets.append(temp_way)
        else: 
            for s in range(len(set_indexes)):
                set_ways = cache.data[set_indexes[s]].keys()
                temp_way = ["Set " + str(s)]
                for w in set_ways:
                    temp_way.append(cache.data[set_indexes[s]][w].address)
                sets.append(temp_way)

        table = UnixTable(sets)
        table.title = cache.name
        table.inner_row_border = True
        print ("\n")
        print (table.table)

#Loop through the instructions in the tracefile and use
#the given memory hierarchy to find AMAT
def simulate(hierarchy, trace, logger):
    responses = []
    #We only interface directly with L1. Reads and writes will automatically
    #interact with lower levels of the hierarchy
    l1 = hierarchy['cache_1']
    for current_step in range(len(trace)):
        instruction = trace[current_step]
        address, op = instruction.split()
        #Call read for this address on our memory hierarchy
        if op == 'R':
            logger.info(str(current_step) + ':\tReading ' + address)
            r = l1.read(address, current_step)
            logger.warning('\thit_list: ' + pprint.pformat(r.hit_list) + '\ttime: ' + str(r.time) + '\n')
            responses.append(r)
        #Call write
        elif op == 'W':
            logger.info(str(current_step) + ':\tWriting ' + address)
            r = l1.write(address, True, current_step)
            logger.warning('\thit_list: ' + pprint.pformat(r.hit_list) + '\ttime: ' + str(r.time) + '\n')
            responses.append(r)
        else:
            raise InvalidOpError
    logger.info('Simulation complete')
    analyze_results(hierarchy, responses, logger)

def analyze_results(hierarchy, responses, logger):
    #Parse all the responses from the simulation
    n_instructions = len(responses)

    total_time = 0
    for r in responses:
        total_time += r.time
    logger.info('\nNumber of instructions: ' + str(n_instructions))
    logger.info('\nTotal cycles taken: ' + str(total_time) + '\n')

    amat = compute_amat(hierarchy['cache_1'], responses, logger)
    logger.info('\nAMATs:\n'+pprint.pformat(amat))

def compute_amat(level, responses, logger, results={}):
    #Check if this is main memory
    #Main memory has a non-variable hit time
    if not level.next_level:
        results[level.name] = level.hit_time
    else:
        #Find out how many times this level of cache was accessed
        #And how many of those accesses were misses
        n_miss = 0
        n_access = 0
        for r in responses:
            if level.name in r.hit_list.keys():
                n_access += 1
                if r.hit_list[level.name] == False:
                    n_miss += 1

        if n_access > 0:
            miss_rate = float(n_miss)/n_access
            #Recursively compute the AMAT of this level of cache by computing
            #the AMAT of lower levels
            results[level.name] = level.hit_time + miss_rate * compute_amat(level.next_level, responses, logger)[level.next_level.name] #wat
        else:
            results[level.name] = 0 * compute_amat(level.next_level, responses, logger)[level.next_level.name] #trust me, this is good

        logger.info(level.name)
        logger.info('\tNumber of accesses: ' + str(n_access))
        logger.info('\tNumber of hits: ' + str(n_access - n_miss))
        logger.info('\tNumber of misses: ' + str(n_miss))
    return results


def build_hierarchy(configs, logger):
    #Build the cache hierarchy with the given configuration
    hierarchy = {} # 캐시 계층 만들기 1level, 2level etc...
    #Main memory is required
    main_memory = build_cache(configs, 'mem', None, logger)
    prev_level = main_memory
    hierarchy['mem'] = main_memory
    if 'cache_4' in configs.keys():
        cache_4 = build_cache(configs, 'cache_4', prev_level, logger)
        prev_level = cache_4
        hierarchy['cache_4'] = cache_4
    if 'cache_3' in configs.keys():
        cache_3 = build_cache(configs, 'cache_3', prev_level, logger)
        prev_level = cache_3
        hierarchy['cache_3'] = cache_3
    if 'cache_2' in configs.keys():
        cache_2 = build_cache(configs, 'cache_2', prev_level, logger)
        prev_level = cache_2
        hierarchy['cache_2'] = cache_2
    #Cache_1 is required
    cache_1 = build_cache(configs, 'cache_1', prev_level, logger)
    hierarchy['cache_1'] = cache_1
    return hierarchy

def build_cache(configs, name, next_level_cache, logger):
    return cache.Cache(name,
                configs['architecture']['word_size'],   # 컴퓨터에서 데이터를 처리하는 기본 단위
                configs['architecture']['block_size'],  # 운영 체제 또는 프로그램이 기억공간을 임의적으로 분할하여 사용하는 하나의 단위
                configs[name]['blocks'] if (name != 'mem') else -1, # 블록의 수 
                configs[name]['associativity'] if (name != 'mem') else -1,   # 몇 way assiciativity 인지
                configs[name]['hit_time'],
                configs[name]['hit_time'],
                configs['architecture']['write_back'], # write back이면 캐시만 업데이트, write through면 캐시와 메모리 모두 업데이트
                logger,     # 로그 파일 저장 그거 
                next_level_cache) # 이전 레벨의 캐시는 무엇인지 


if __name__ == '__main__':
    main()

import datetime
import json
import os
import re
import threading
import tkinter as tk
from typing import Union
import locale

import requests
from tkcalendar import DateEntry

from utils import get_config
from utils import get_url_with_tries

config = get_config()
kaspa_api_url = config['kaspa_api_url']


class MyForm:
    def __init__(self) -> None:
        self.window = None
        self.log_text = None
        self.input_text = None
        self.input_hashrate = None
        self.start_date = None
        self.end_date = None
        self.submit_button = None

    def create_window(self) -> None:
        self.window = tk.Tk()
        self.window.title('Real revenue calculator')
        self.window.grid_columnconfigure(0, weight=0, minsize=400)
        self.window.grid_columnconfigure(1, weight=1, minsize=500)
        self.window.grid_rowconfigure(0, weight=1, minsize=500)

    def create_widgets(self) -> None:
        left_frame = tk.Frame(self.window)
        left_frame.grid(row=0, column=0, padx=0, pady=10, sticky='nw')
        self.input_text = tk.Text(left_frame, width=100, height=25)
        input_label = tk.Label(left_frame, text='Kaspa link to pool addresses')
        input_label.grid(row=1, column=0, padx=10, pady=(10, 0), sticky='w')
        self.input_text.grid(row=2, column=0, padx=10, pady=(0, 10), sticky='w')
        self.input_hashrate = tk.Entry(left_frame, width=20)
        if config['custom_hashrate'] > 0:
            self.input_hashrate.insert(1, config['custom_hashrate'])
        input_label = tk.Label(left_frame, text='Custom hashrate GH/s:')
        input_label.grid(row=7, column=0, padx=10, pady=(10, 0), sticky='w')
        self.input_hashrate.grid(row=8, column=0, padx=10, pady=(0, 10), sticky='w')
        start_date_value = datetime.datetime.today() - datetime.timedelta(days=7)
        self.start_date = DateEntry(
            left_frame,
            width=12,
            background='darkblue',
            foreground='white',
            borderwidth=2,
            date_pattern='yyyy-mm-dd'
        )
        self.start_date.set_date(start_date_value)
        start_date_label = tk.Label(left_frame, text='Start Date:')
        start_date_label.grid(row=3, column=0, padx=10, pady=(10, 0), sticky='w')
        self.start_date.grid(row=4, column=0, padx=10, pady=(0, 10), sticky='w')
        self.end_date = DateEntry(
            left_frame,
            width=12,
            background='darkblue',
            foreground='white',
            borderwidth=2,
            date_pattern='yyyy-mm-dd'
        )
        end_date_label = tk.Label(left_frame, text='End Date:')
        end_date_label.grid(row=5, column=0, padx=10, pady=(10, 0), sticky='w')
        self.end_date.grid(row=6, column=0, padx=10, pady=(0, 10), sticky='w')
        self.submit_button = tk.Button(left_frame, text='Submit', command=submit_thread)
        self.submit_button.grid(row=9, column=0, padx=10, pady=10, sticky='w')
        log_frame = tk.Frame(self.window)
        log_frame.grid(row=0, column=1, padx=10, pady=10, sticky='nsew')
        self.log_text = tk.Text(log_frame, height=15, width=40)
        self.log_text.pack(side='left', fill='both', expand=True)
        log_scrollbar = tk.Scrollbar(log_frame, orient='vertical', command=self.log_text.yview)
        log_scrollbar.pack(side='right', fill='y')
        self.log_text.config(yscrollcommand=log_scrollbar.set)
        self.input_text.insert(1.0, config['kaspa_address'])

    def print_to_log(self, *args) -> None:
        text = ' '.join(str(arg) for arg in args)
        self.log_text.insert(tk.END, f'{text}\n')
        self.log_text.see(tk.END)

    def run(self) -> None:
        self.create_window()
        self.create_widgets()
        self.window.mainloop()


def submit_thread(*args, **kwargs) -> None:
    threading.Thread(target=submit, args=args, kwargs=kwargs).start()


def do_calcs_for_address(kaspa_address: str, force_hashrate: float) -> tuple[dict, str]:
    period_start_t = int(datetime.datetime.combine(form.start_date.get_date(), datetime.time.min).timestamp())
    period_end_t = int(datetime.datetime.combine(form.end_date.get_date(), datetime.time.max).timestamp())
    if 'woolypooly' in kaspa_address:
        pool = 'woolypooly'
    elif 'kaspa-pool' in kaspa_address:
        pool = 'kaspa-pool'
    elif 'k1pool' in kaspa_address:
        pool = 'k1pool'
    elif 'acc-pool' in kaspa_address:
        pool = 'acc-pool'
    elif 'hero' in kaspa_address:
        pool = 'hero'
    else:
        pool = 'other'
    kaspa_address, user_hashrate = get_hashrate_from_pool(kaspa_address)
    form.print_to_log(f'Kaspa Address is: {kaspa_address}')
    form.print_to_log(f'24h hashrate is: {round(user_hashrate, 4)}')
    tx_count = get_tx_count_from_kaspa_api(kaspa_address)
    period_start = datetime.datetime.fromtimestamp(period_start_t).strftime('%Y-%m-%d %H:%M:%S')
    period_end = datetime.datetime.fromtimestamp(period_end_t).strftime('%Y-%m-%d %H:%M:%S')
    form.print_to_log(f'{period_start_t} {period_end_t}')
    if tx_count > 5_000:
        limit_range = 500
    else:
        limit_range = 100
    total_transactions, offset = calculate_range(kaspa_address, period_start_t, period_end_t, tx_count, limit_range)
    if total_transactions + offset > tx_count:
        total_transactions = tx_count - offset
        form.print_to_log(f'You set too much transactions... Only {total_transactions} '
                          f'can be parsed based on offset. Changed to this value')
    limit = 100
    miner_stat_data = get_data_from_minerstat()
    kaspa_explorer_data = get_transactions_from_kaspa_api(kaspa_address, total_transactions, limit, offset)
    # filter_inputs(kaspa_explorer_data)
    grouped_transactions, tx_count, tx_completed = group_transactions(
        kaspa_address,
        kaspa_explorer_data,
        period_start_t,
        period_end_t
    )
    return do_calculate(
        kaspa_address,
        user_hashrate,
        grouped_transactions,
        miner_stat_data,
        tx_count,
        tx_completed,
        period_start,
        period_end,
        total_transactions,
        limit,
        offset,
        pool
    )


def submit() -> None:
    export_final = list()
    period_start = form.start_date.get_date()
    period_end = form.end_date.get_date()
    form.submit_button['state'] = 'disabled'
    kaspa_addresses = form.input_text.get('1.0', 'end-1c')
    top_line = 'Date;'
    bottom_line = 'Average percent;'
    if 'pplns' in kaspa_addresses:
        kaspa_addresses = json.loads(kaspa_addresses)['pplns']['default']
        for kaspa_address in kaspa_addresses:
            tx_count = get_tx_count_from_kaspa_api(kaspa_address['miner'])
            if tx_count < 2000:
                export_lines, average_percent = do_calcs_for_address(
                    kaspa_address['miner'],
                    int(kaspa_address['hashrate']) / 1_000_000
                )
                export_final.append(export_lines)
                top_line += f'{kaspa_address["miner"]};'
                bottom_line += f'{average_percent};'
    else:
        kaspa_addresses = kaspa_addresses.splitlines()
        for kaspa_address in kaspa_addresses:
            export_lines, average_percent = do_calcs_for_address(kaspa_address, 0)
            export_final.append(export_lines)
            top_line += f'{kaspa_address};'
            bottom_line += f'{average_percent};'
    current_date = period_end
    result = ''
    dt_now_str = datetime.datetime.now().strftime('%Y-%m-%d_%H-%M-%S')
    filepath = f'pool_results/summary/csv/{dt_now_str}.csv'
    while current_date >= period_start:
        line = ''
        for export_record in export_final:
            revenue_percent = export_record.get(current_date.strftime('%Y-%m-%d'), '')
            line += f'{revenue_percent};'
        result += f'{current_date};{line}\n'
        dt_now_str = datetime.datetime.now().strftime('%Y-%m-%d_%H-%M-%S')
        filepath = f'pool_results/summary/csv/{dt_now_str}.csv'
        if not os.path.exists('pool_results/summary'):
            os.mkdir('pool_results/summary')
        if not os.path.exists('pool_results/summary/csv'):
            os.mkdir('pool_results/summary/csv')
        current_date -= datetime.timedelta(days=1)
    with open(filepath, 'w') as f:
        f.write(top_line + '\n')
        f.write(result)
        f.write(bottom_line)

    form.print_to_log('JOB FINISHED!')
    form.print_to_log(f'Report exported to {filepath}!')
    form.submit_button['state'] = 'active'


def get_hashrate_from_pool(kaspa_address: str) -> tuple[str, float]:
    hashrate = 0
    custom_hashrate = str(form.input_hashrate.get()).replace(',','.')
    if custom_hashrate != '':
        hashrate = float(custom_hashrate)

    if 'acc-pool.pw' in kaspa_address:
        kaspa_address = kaspa_address.split('/')[-2]
        if hashrate == 0:
            response = requests.get(f'https://kaspa.acc-pool.pw/miners/{kaspa_address}')
            data = response.text
            kaspa_address = f'kaspa:{kaspa_address}'
            parsed_data = data.split('name: "Average hashrate",')
            parsed_data = parsed_data[1]
            parsed_data = parsed_data.split('}]')[0]
            parsed_data = re.sub(r'\t\t\t\t', r'', parsed_data)
            parsed_data = parsed_data.split('data: ')[1].split('}]')[0]
            parsed_data = re.sub(r'\t\t\t\t', r'', parsed_data)
            parsed_data = parsed_data.split(']]')[0] + ']]'
            data = json.loads(parsed_data)
            for i in range(len(data) - 24, len(data)):
                hashrate += data[i][1]
            hashrate = hashrate / 24

    elif 'woolypooly' in kaspa_address:
        kaspa_address = kaspa_address.replace('kaspa%3A', 'kaspa:')
        kaspa_address = kaspa_address.split('/')[-1]
        if hashrate == 0:
            response = requests.get(f'https://api.woolypooly.com/api/kas-1/accounts/{kaspa_address}')
            data = response.json()
            hashrate = data['mode_stats']['pplns']['default']['dayHashrate'] / 1_000_000

    elif 'hero' in kaspa_address:
        kaspa_address = kaspa_address.replace('hero*', '')
        if hashrate == 0:
            response = requests.get(f'https://kaspa.herominers.com/api/stats_address?address={kaspa_address}&recentBlocksAmount=20&longpoll=false')
            data = response.json()
            hashrate = data['stats']['hashrate_24h'] / 1_000_000

    elif 'kaspa-pool.org' in kaspa_address:
        kaspa_address = kaspa_address.split('/')[-1]
        if hashrate == 0:
            params = {'wallet': kaspa_address}
            response = requests.get(f'https://kaspa-pool.org/api/user/base/', params=params)
            data = response.json()
            hash_rate_unit = data['hashrate24h']['hashrate_unit']
            hashrate = data['hashrate24h']['hashrate']
            if hash_rate_unit == 'TH/s':
                hashrate = hashrate * 1_000_000
            if hash_rate_unit == 'GH/s':
                hashrate = hashrate * 1_000

    elif 'k1pool.com' in kaspa_address:
        kaspa_address_pure = kaspa_address.split('/')[-1]
        kaspa_address = f'kaspa:{kaspa_address_pure}'
        if hashrate == 0:
            response = requests.get(f'https://k1pool.com/api/miner/kaspa/{kaspa_address_pure}')
            data = response.json()
            hashrate = data['miner']['dayHashrate'] / 1_000_000
    return kaspa_address, hashrate


def do_average_revenue_minerstat(
        minerstat_data: list,
        start_time: datetime.datetime,
        end_time: datetime.datetime
) -> tuple[int, float]:
    average_time = 0
    average_revenue = 0
    iterations = 0
    for i in range(0, len(minerstat_data)):
        if start_time < minerstat_data[i][0] < end_time:
            iterations += 1
            average_time += minerstat_data[i][0]
            average_revenue += minerstat_data[i][1]
    return int(average_time / iterations), average_revenue / iterations


def get_timestamp(time_string: str) -> int:
    try:
        time_stamp = int(datetime.datetime.strptime(time_string, '%Y-%m-%d %H:%M:%S').timestamp())
    except ValueError:
        try:
            time_stamp = int(datetime.datetime.strptime(time_string, '%Y-%m-%d').timestamp())
        except ValueError:
            raise ValueError('Invalid date format')
    return int(time_stamp)


def get_kaspa_api_data_step(kaspa_address: str, limit: int, offset: int, fields: str) -> Union[dict, list]:
    url = f'{kaspa_api_url}/addresses/{kaspa_address}/full-transactions'
    params = {'limit': limit, 'offset': offset, 'fields': fields}
    return get_url_with_tries(url=url, params=params)


def get_tx_count_from_kaspa_api(kaspa_address: str) -> int:
    form.print_to_log('api.kaspa.org: getting tx count...')
    url = f'{kaspa_api_url}/addresses/{kaspa_address}/transactions-count'
    tx_count = int(get_url_with_tries(url=url)['total'])
    form.print_to_log(f'{tx_count} transactions found')
    return tx_count


def get_data_from_minerstat(local_data: bool = False) -> list:
    form.print_to_log('Parsing data from api.minerstat.com...')
    minerstat_ts = f'2{datetime.datetime.now().timestamp()}'
    if local_data:
        # https://api.minerstat.com/v2/coins-history?time=21677558600&coin=KAS&algo=KHeavyHash
        with open('chart.json', 'r') as f:
            data = json.loads(f.read())
    else:
        params = {'time': minerstat_ts, 'coin': 'KAS', 'algo': 'KHeavyHash'}
        response = requests.get('https://api.minerstat.com/v2/coins-history', params=params)
        data = response.json()
    miner_stat_data = list()
    for item in data['KAS']:
        miner_stat_data.append([int(item), float(data['KAS'][item][2]) * 24])
    return miner_stat_data


def calculate_range(
        kaspa_address: str,
        period_start_t: int,
        period_end_t: int,
        tx_count: int,
        limit: int = 100
) -> tuple[int, int]:
    offset = 0
    iteration = 0
    end_limit = limit
    while True:
        data = get_kaspa_api_data_step(kaspa_address, 1, offset, 'block_time')
        block_time = round(data[0]['block_time'] / 1_000)
        iteration += 1
        if iteration > 5:
            limit = 1_000
        if iteration > 8:
            limit = 3_000
        if iteration > 11:
            limit = 5_000
        form.print_to_log(f'Calculating offset : {block_time} {period_end_t} {offset}')
        if block_time < period_end_t:
            start = offset
            break
        offset += limit
    iteration = 0
    limit = end_limit
    while True:
        if block_time < period_start_t:
            end = offset
            break
        offset += limit
        if offset >= tx_count:
            end = tx_count - 1
            break
        block_time = get_kaspa_api_data_step(kaspa_address, 1, offset, 'block_time')
        block_time = round(block_time[0]['block_time'] / 1_000)
        iteration += 1
        if iteration > 5:
            limit = 1_000
        if iteration > 8:
            limit = 3_000
        if iteration > 11:
            limit = 5_000
        form.print_to_log(f'Calculating count : {block_time} {period_end_t} {offset}')
    count = end - start + limit
    offset = start - limit
    if offset < 0:
        offset = 0
    return count, offset


def get_transactions_from_kaspa_api(kaspa_address: str, total_transactions: int, limit: int, offset: int) -> list:
    current_step = 1
    kaspa_explorer_data = 0
    form.print_to_log('Parsing data from api.kaspa.org...')
    remain_transactions = total_transactions
    while remain_transactions > 0:
        if limit >= remain_transactions:
            limit = remain_transactions
        data = get_kaspa_api_data_step(kaspa_address, limit, offset, 'transaction_id,block_time,outputs')
        if limit != remain_transactions - 1:
            form.print_to_log(f'Step: {current_step}/{round(total_transactions / limit)}\t\t'
                              f'Transactions remain:{remain_transactions}')
        if kaspa_explorer_data == 0:
            try:
                kaspa_explorer_data = data
                remain_transactions -= limit
                offset += limit
                current_step += 1
            except:
                form.print_to_log('Main: Load data corrupted. Retrying...')
        else:
            try:
                kaspa_explorer_data += data
                remain_transactions -= limit
                offset += limit
                current_step += 1
            except:
                form.print_to_log('Load failed. Retrying...')
    kaspa_explorer_data = list(reversed(kaspa_explorer_data))
    return kaspa_explorer_data


def group_transactions(
        kaspa_address: str,
        kaspa_explorer_data: list,
        period_start_t: int,
        period_end_t: int,
) -> tuple[dict, int, int]:
    tx_id_array = list()
    tx_cursor = 0
    tx_completed = 0
    total_amount = 0
    first_time = 0
    last_time = 0
    time_marker = 0
    gr_date = 0
    combined_transactions = 0
    grouped_transactions = dict()
    tx_count = len(kaspa_explorer_data)
    for transaction in kaspa_explorer_data:
        tx_id = transaction['transaction_id']
        tx_cursor += 1
        if tx_id not in tx_id_array:
            tx_completed += 1
            tx_id_array.append(tx_id)
            tx_time = int(transaction['block_time'] / 1_000)
            tx_date = datetime.datetime.fromtimestamp(tx_time).strftime('%Y-%m-%d')
            if period_start_t < tx_time < period_end_t:
                if time_marker == 0:
                    time_marker = tx_date
                for output in transaction['outputs']:
                    if output['script_public_key_address'] == kaspa_address:
                        tx_time = int(transaction['block_time'] / 1_000)
                        if period_start_t < tx_time < period_end_t:
                            form.print_to_log(f'{tx_date} {tx_id} {output["amount"]}')
                            if first_time == 0 or tx_cursor == 1:
                                first_time = tx_time
                                form.print_to_log('First time init...')
                            else:
                                if total_amount > 0 and gr_date != tx_date:
                                    form.print_to_log('Grouping')
                                    grouped_transactions[gr_date] = [gr_date, total_amount, first_time, last_time]
                                    first_time = last_time
                                    total_amount = 0
                                    combined_transactions = 0
                                form.print_to_log('Adding...')
                                last_amount = output['amount'] / 100_000_000
                                total_amount += last_amount
                                last_time = tx_time
                                gr_date = tx_date
                                combined_transactions += 1
    if total_amount > 0:
        grouped_transactions[gr_date] = [gr_date, total_amount, first_time, last_time]
        form.print_to_log('Finishing...')
    form.print_to_log(f'Transactions proceed: {tx_completed}')
    form.print_to_log(f'Dubbed transactions(skipped): {tx_count - tx_completed}')
    return grouped_transactions, tx_count, tx_completed


def do_calculate(
        kaspa_address: str,
        user_hashrate: int,
        grouped_transactions: dict,
        minerstat_data: list,
        tx_count: int,
        tx_completed: int,
        period_start: str,
        period_end: str,
        total_transactions: int,
        limit: int,
        offset: int,
        pool: str
) -> tuple[dict, str]:
    now = datetime.datetime.now()
    folder_name = kaspa_address.replace('kaspa:', '')
    report_date = now.strftime('%Y-%m-%d %H:%M:%S')
    file_name = now.strftime('%Y-%m-%d_%H-%M-%S')
    file_path = f'pool_results/{pool}/{folder_name}/{file_name}-{folder_name}.csv'
    if not os.path.exists('pool_results'):
        os.mkdir('pool_results')
    if not os.path.exists(f'pool_results/{pool}'):
        os.mkdir(f'pool_results/{pool}')
    if not os.path.exists(f'pool_results/{pool}/{folder_name}'):
        os.mkdir(f'pool_results/{pool}/{folder_name}')
    average_percent = 0
    result = 'DATE;Amount received; Amount expected; %\n'
    export_result = dict()
    if locale.getdefaultlocale()[0] == 'ru_RU':
        decimal_point = ','
    else:
        decimal_point = '.'
    for key in grouped_transactions:
        value = grouped_transactions[key]
        average_time, average_revenue = do_average_revenue_minerstat(minerstat_data, value[2], value[3])
        tx_average_revenue = average_revenue * user_hashrate * 1_000_000 / 24 / 3_600 * (value[3] - value[2])
        date = value[0]

        fact_revenue = str(round(value[1], 2)).replace('.', decimal_point)
        expected_revenue = str(round(tx_average_revenue, 2)).replace('.', decimal_point)
        percent = -round((1 - value[1] / tx_average_revenue) * 100, 2)
        average_percent += percent
        percent_str = str(percent).replace('.', decimal_point)
        form.print_to_log(f'{date}\t{fact_revenue}\t{expected_revenue}\t{percent_str}')
        result += f'{date};{fact_revenue};{expected_revenue};{percent_str}\n'
        export_result[date] = percent_str
    average_percent = str(round(average_percent / len(grouped_transactions), 2)).replace('.', decimal_point)
    form.print_to_log(f'Average percent: {average_percent}')
    form.print_to_log(f'Exported to {file_path}')
    result += f'\nReport date: {report_date}'
    result += f'\nPool: {pool}'
    result += f'\nKaspa address: {kaspa_address}'
    result += f'\nAverage percent: {average_percent}\n'
    result += '\nTransactions count;Limit;Offset;Hashrate;Period start;Period end;TX proceed;TX skipped\n'
    result += f'{total_transactions};{limit};{offset};{user_hashrate};' \
              f'{period_start};{period_end};{tx_completed};{tx_count - tx_completed}'
    with open(file_path, 'w') as f:
        f.write(result)
    return export_result, average_percent


def filter_inputs(kaspa_explorer_data: list) -> None:
    tx_unique = list()
    for transaction in kaspa_explorer_data:
        tx_id = transaction['transaction_id']
        if tx_id not in tx_unique:
            tx_unique.append(tx_id)
    form.print_to_log('Filtering input transactions...')
    url = f'{kaspa_api_url}/transactions/search'
    headers = {
        'accept': 'application/json',
        'Content-Type': 'application/json'
    }
    data = {'transactionIds': tx_unique}
    response = requests.post(url, headers=headers, json=data)
    form.print_to_log(response.json())


if __name__ == '__main__':
    form = MyForm()
    form.run()

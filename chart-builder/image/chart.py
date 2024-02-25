import csv
import datetime
import logging
import matplotlib.pyplot as plt
import numpy as np

# Enable logging
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)

def read_csv(file_path, limit=1000000):
    data = {'dates': [], 'buy_rate': [], 'sell_rate': [], 'buy_rate_eur': [], 'sell_rate_eur': [], 'pln_exchange_rate': []}

    logging.info(f'Reading CSV file: {file_path}')
    with open(file_path, newline='') as csvfile:
        reader = csv.reader(csvfile)
        next(reader)  # Skip header if present

        lines = list(reader)
        num_lines = len(lines)
        logging.info(f'Number of lines in CSV file: {num_lines}')

        if num_lines > limit:
            lines = lines[-limit:]
            logging.info(f'Limiting data to last {limit} entries')

        for row in lines:
            date, buy_rate, sell_rate, buy_rate_eur, sell_rate_eur, pln_exchange_rate = row
            date = datetime.datetime.strptime(date, '%Y-%m-%d %H:%M:%S').strftime('%Y-%m-%d %H:%M')
            data['dates'].append(date)
            data['buy_rate'].append(float(buy_rate))
            data['sell_rate'].append(float(sell_rate))
            data['buy_rate_eur'].append(float(buy_rate_eur))
            data['sell_rate_eur'].append(float(sell_rate_eur))
            data['pln_exchange_rate'].append(float(pln_exchange_rate))

    return data

def downsample_data(data):
    dates = data['dates']
    pln_exchange_rate = data['pln_exchange_rate']
    num_points = len(dates)

    if num_points <= 100:
        factor = 1
    elif 100 < num_points <= 500:
        factor = 20
    elif 500 < num_points <= 1000:
        factor = 50
    elif 1000 < num_points <= 10000:
        factor = 75
    else:
        factor = max(100, num_points // 250)
    
    logging.info(f'Downsampling data with factor: {factor}')

    num_aggregated_points = num_points // factor

    aggregated_dates = []
    aggregated_pln_exchange_rate = []

    for i in range(num_aggregated_points):
        start_index = i * factor
        end_index = start_index + factor

        aggregated_dates.append(dates[start_index])
        aggregated_pln_exchange_rate.append(np.mean(pln_exchange_rate[start_index:end_index]))

    return {'dates': aggregated_dates, 'pln_exchange_rate': aggregated_pln_exchange_rate}

def create_chart(data, output_file):
    downsampled_data = downsample_data(data)

    logging.info('Creating a plot for PLN exchange rates over time.')

    plt.figure(figsize=(16, 9))
    plt.plot(downsampled_data['dates'], downsampled_data['pln_exchange_rate'], label='PLN/UAH Rate over time', marker='o')

    # Customize chart
    plt.title('Exchange Rates Over Time')
    plt.xlabel('Time')
    plt.ylabel('Exchange Rate')
    plt.legend()
    plt.xticks(rotation=45, ha='right')  # Rotate x-axis labels for better readability

    # Save the chart as an image file
    plt.tight_layout()
    plt.savefig(output_file)
    plt.close()

if __name__ == "__main__":
    # Update the file path with your CSV file
    csv_file_path = '../data/exchange_rates.csv'
    output_file = '../data/chart.png'

    # Read data from CSV
    try:
        exchange_data = read_csv(csv_file_path, limit=100000)
    except Exception as e:
        logging.error(f'Error reading CSV file: {str(e)}')
        exit(1)
    
    # Save the chart as an image file (change 'chart.png' to your desired filename)
    try:
        create_chart(exchange_data, output_file)
        logging.info(f'Chart created successfully: {output_file}')
        exit(0)
    except Exception as e:
        logging.error(f'Error creating chart: {str(e)}')
        exit(1)
import pandas as pd


def parse_csv(file_path):
      # CVS Column Names
      col_names = ['company_name', 'symbol']
      # Use Pandas to parse the CSV file
      csv_data = pd.read_csv(file_path,names=col_names, header=None)
      # Loop through the Rows
      csv_parsed_data = []
      for i,row in csv_data.iterrows():
         csv_parsed_data.append({
            'symbol': i[0], # holding Symbol means first column of csv
            'company': i[1] # holding company name means second column of csv
         })
      return csv_parsed_data
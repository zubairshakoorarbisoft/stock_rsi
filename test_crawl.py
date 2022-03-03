
import os
from selenium import webdriver
from selenium.webdriver.support.select import Select
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager

options = webdriver.ChromeOptions()
options.add_argument('--ignore-certificate-errors-spki-list')
options.add_argument('--ignore-ssl-errors')
options.add_experimental_option('excludeSwitches', ['enable-logging'])
driver_path = '/Users/zubairshakoor/Documents/D/Zubair/Extras/Projects/stock_rsi/chromedriver.exe'
breakpoint()
driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()), chrome_options=options)
driver.get('https://www.google.com/')
breakpoint()
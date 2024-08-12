import time
import os
import decimal
import random
import requests
import json
from dotenv import load_dotenv
from eth_account import Account
from colorama import Fore, Style, init
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime

init(autoreset=True)
load_dotenv()

# Membaca konfigurasi dari file JSON
with open('config.json', 'r') as f:
    config = json.load(f)

WAKTU_PENGIRIMAN = config["WAKTU_PENGIRIMAN"]
WAKTU_PENGULANGAN = config["WAKTU_PENGULANGAN"]
MAKS_PENGULANGAN = config["MAKS_PENGULANGAN"]
JUMLAH_TRANSAKSI_PER_AKUN = config["JUMLAH_TRANSAKSI_PER_AKUN"]
BATAS_GAS = config["BATAS_GAS"]
HARGA_GAS = config["HARGA_GAS"]
URL_RPC = config["URL_RPC"]
ID_RANTAI = config["ID_RANTAI"]
JUMLAH_KIRIM = config["JUMLAH_KIRIM"]

def load_accounts_from_env():
    accounts = []
    i = 1
    while True:
        private_key = os.getenv(f"PRIVATE_KEY_{i}")
        if not private_key:
            break
        account = Account.from_key(private_key)
        accounts.append({"address": account.address, "private_key": private_key})
        i += 1
    return accounts

ACCOUNTS = load_accounts_from_env()

if not ACCOUNTS:
    print(Fore.RED + "Error: No accounts loaded from environment variables.")
    exit(1)

def log(message, level="INFO"):
    timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    levels = {
        "INFO": Fore.CYAN + "INFO",
        "SUCCESS": Fore.GREEN + "SUCCESS",
        "WARNING": Fore.YELLOW + "WARNING",
        "ERROR": Fore.RED + "ERROR"
    }
    print(f"{timestamp} | {levels.get(level, 'INFO')} | {message}")

def buat_alamat_eth_baru():
    akun_baru = Account.create()
    return akun_baru.address

def permintaan_dengan_pengulangan(data, pengulangan=15, tunda=3):
    for percobaan in range(pengulangan):
        try:
            respon = requests.post(URL_RPC, json=data)
            respon.raise_for_status()
            return respon.json()
        except requests.exceptions.RequestException as e:
            log(f"HTTP Error: {e}", "WARNING")
            if percobaan < pengulangan - 1:
                log(f"Retrying in {tunda} seconds...", "INFO")
                time.sleep(tunda)
            else:
                raise

def periksa_saldo(alamat):
    data = {"jsonrpc": "2.0", "method": "eth_getBalance", "params": [alamat, "latest"], "id": 1}
    respon_json = permintaan_dengan_pengulangan(data)
    if "result" in respon_json:
        saldo = int(respon_json["result"], 16)
        return decimal.Decimal(saldo) / 10**18
    else:
        log(f"Unexpected response format: {respon_json}", "ERROR")
        raise Exception("No result field in JSON response")

def dapatkan_nonce(alamat):
    data = {"jsonrpc": "2.0", "method": "eth_getTransactionCount", "params": [alamat, "pending"], "id": 1}
    respon_json = permintaan_dengan_pengulangan(data)
    return int(respon_json["result"], 16)

def kirim_transaksi_dengan_delay(account, nonce, alamat_penerima):
    jumlah_kirim_acak = decimal.Decimal(random.uniform(0.0000001, 0.0000005))
    jumlah_kirim_acak_wei = int(jumlah_kirim_acak * 10**18)
    transaksi = {
        'nonce': nonce,
        'to': alamat_penerima,
        'value': hex(jumlah_kirim_acak_wei),
        'gas': hex(BATAS_GAS),
        'gasPrice': hex(HARGA_GAS),
        'chainId': ID_RANTAI
    }
    transaksi_ttd = Account.sign_transaction(transaksi, account["private_key"])
    data_transaksi = transaksi_ttd.rawTransaction.hex()
    data = {"jsonrpc": "2.0", "method": "eth_sendRawTransaction", "params": [data_transaksi], "id": 1}
    respon_json = permintaan_dengan_pengulangan(data)
    if "result" in respon_json:
        return respon_json["result"]
    elif "error" in respon_json and respon_json["error"]["message"] == "Known transaction":
        log("Transaction known, proceeding to next transaction.", "WARNING")
        return None
    else:
        raise Exception(respon_json["error"]["message"])

def proses_kirim_transaksi_per_akun(account):
    log(f"===== Starting Transaction Sending for Account {account['address']} =====", "INFO")
    for i in range(1, JUMLAH_TRANSAKSI_PER_AKUN + 1):
        try:
            saldo = periksa_saldo(account["address"])
            saldo_diperlukan = decimal.Decimal(BATAS_GAS) * decimal.Decimal(HARGA_GAS) / 10**18
            if saldo < saldo_diperlukan:
                log(f"Insufficient balance for transaction {i}. Required balance: {saldo_diperlukan}, Current balance: {saldo}.", "ERROR") 
                break

            alamat_penerima = buat_alamat_eth_baru()
            nonce = dapatkan_nonce(account["address"])
            hash_tx = kirim_transaksi_dengan_delay(account, nonce, alamat_penerima)
            if hash_tx:
                log(f"Transaction {i} sent. Account: {account['address']}, Nonce: {nonce}, Receiver Address: {alamat_penerima}, Hash: {hash_tx}", "SUCCESS")
                delay = random.randint(1, 5)
                log(f"Waiting for {delay} seconds before next transaction...", "INFO")
                time.sleep(delay)
        except Exception as e:
            log(f"Error sending transaction {i} for account {account['address']}: {e}", "ERROR")

    log(f"===== Transaction Sending Completed for Account {account['address']} =====", "INFO")

def utama():
    with ThreadPoolExecutor(max_workers=len(ACCOUNTS)) as executor:
        futures = [executor.submit(proses_kirim_transaksi_per_akun, account) for account in ACCOUNTS]
        for future in as_completed(futures):
            future.result()

if __name__ == "__main__":
    utama()

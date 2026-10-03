import requests, time
TOKEN = "8446878675:AAG00SXde7Xk8EfQA7A_CYjF_cCLattXCvI"
URL = f"https://api.telegram.org/bot{TOKEN}/"
print("Бот запущен!")
offset = 0
while True:
    try:
        r = requests.get(URL + "getUpdates", params={"offset": offset, "timeout": 30}).json()
        for res in r.get("result", []):
            offset = res["update_id"] + 1
            m = res.get("message")
            if m and "text" in m:
                requests.post(URL + "sendMessage", json={"chat_id": m["chat"]["id"], "text": "Эхо: " + m["text"]})
    except Exception as e:
        print(e)
        time.sleep(3)

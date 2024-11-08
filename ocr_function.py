#ライブラリのインポート
import streamlit as st
import pandas as pd
import os
import base64
import requests
from io import StringIO
from datetime import datetime
from PIL import Image

# OpenAI API Key
api_key = st.secrets["API"]

# プロンプト（商品名、価格、個数を抽出する）
extract_prompt = """
    入力画像はレシートの画像です。この画像から次の条件に従って商品名、価格、個数を抽出してください。
    余計な文章は生成しない
    - 出力形式: 各商品名、価格、個数をカンマで区切った形式で出力（例: 商品名1, 価格1, 個数1）
    - 出力項目: 商品名、価格、個数
    - 日本語の他のテキストは出力しない
    - 価格にはカンマを含めないこと
"""

# 商品名とカテゴリーを振り分けるためのプロンプト
category_prompt = """
    次の商品の名前を見て、適切なカテゴリーを振り分けてください。
    余計な文章は生成しない
    - カテゴリーの選択肢: 畜産食品、水産食品、農産食品、果物、穀物、乳製品、加工食品、果物
    - 選択肢が適切でないのものはすべてその他に分類
    - 出力形式: 商品名, カテゴリー
"""

# 商品名から名称を生成するためのプロンプト
name_generation_prompt = """
    次の商品の名前をもとに、商品を表す料理名または食材名に簡略化して生成してください。
    元の名前と同一、またはほとんど同じ名称は避けること
    余計な文章は生成せず、できる限り短く簡潔に
    - 出力形式:生成された名称のみ
"""

def encode_image(image):
    temp_image_path = "temp_image.jpeg"
    image.save(temp_image_path)

    with open(temp_image_path, "rb") as image_file:
        return base64.b64encode(image_file.read()).decode('utf-8')

def ocr_to_csv(uploaded_files, output_folder, output_name):
    concat_df = pd.DataFrame([])
        
    for uploaded_file in uploaded_files:
        
        image = Image.open(uploaded_file)
        base64_image = encode_image(image)

        # APIリクエストのヘッダーとペイロード
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}"
        }

        # 商品名、価格、個数を抽出するためのリクエスト
        payload = {
            "model": "gpt-4o",
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "text",
                            "text": extract_prompt
                        },
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": f"data:image/jpeg;base64,{base64_image}"
                            }
                        }
                    ]
                }
            ],
            "max_tokens": 300
        }

        try:
            response = requests.post("https://api.openai.com/v1/chat/completions", headers=headers, json=payload)
            response.raise_for_status()  # エラーがある場合例外を発生させる
            content = response.json().get('choices')[0]['message']['content'].strip()
        except requests.exceptions.RequestException as e:
            content = ""
            return print(f"APIリクエストに失敗しました: {e}")
        
        # データを手動で分割してリストを作成
        data = [line.split(',') for line in content.split('\n') if line.strip()]

        # 商品名、価格、個数を取得
        product_list = [(item[0].strip(), item[1].strip(), item[2].strip()) if len(item) == 3 else (item[0].strip(), "N/A", "N/A") for item in data]

        # 商品名、価格、個数をそれぞれのリストに分ける
        product_names = [item[0] for item in product_list]
        product_prices = [item[1] for item in product_list]
        product_quantities = [item[2] for item in product_list]

        # カテゴリーを生成するためのリクエスト
        category_payload = {
            "model": "gpt-4o",
            "messages": [
                {
                    "role": "user",
                    "content": f"{category_prompt}\n" + "\n".join(product_names)
                }
            ],
            "max_tokens": 300
        }

        try:
            category_response = requests.post("https://api.openai.com/v1/chat/completions", headers=headers, json=category_payload)
            category_response.raise_for_status()
            category_content = category_response.json().get('choices')[0]['message']['content'].strip()
        except requests.exceptions.RequestException as e:
            category_content = ""
            return print(f"カテゴリー生成リクエストに失敗しました: {e}")

        # 商品名から名称を生成するためのリクエスト
        name_payload = {
            "model": "gpt-4o",
            "messages": [
                {
                    "role": "user",
                    "content": f"{name_generation_prompt}\n" + "\n".join(product_names)
                }
            ],
            "max_tokens": 300
        }

        try:
            name_response = requests.post("https://api.openai.com/v1/chat/completions", headers=headers, json=name_payload)
            name_response.raise_for_status()
            name_content = name_response.json().get('choices')[0]['message']['content'].strip()
        except requests.exceptions.RequestException as e:
            name_content = ""
            return print(f"名称生成リクエストに失敗しました: {e}")
        
        # 商品名、価格、個数、カテゴリーをペアにする
        categorized_data = []
        product_price_index = 0

        # 生成された名称を行ごとに分割
        generated_names = name_content.split('\n')

        # 登録日を生成
        registration_date = datetime.now().strftime("%Y/%m/%d")

        for line in category_content.split('\n'):
            if line.strip():
                product_info = line.split(',')
                product_name = product_info[0].strip()
                category = product_info[1].strip() if len(product_info) > 1 else "N/A"

                # 価格、個数をリストから取得
                price = product_prices[product_price_index] if product_price_index < len(product_prices) else "N/A"
                quantity = product_quantities[product_price_index] if product_price_index < len(product_quantities) else "N/A"

                # 生成された名称を取得
                generated_name = (
                    generated_names[product_price_index].strip() 
                    if product_price_index < len(generated_names) 
                    else "N/A"
                )
                
                categorized_data.append([product_name, price, quantity, category, generated_name, registration_date])
                product_price_index += 1

        # データフレームを作成し、カラム名を設定
        df = df = pd.DataFrame(categorized_data, columns=["商品名", "価格", "個数", "カテゴリー", "名称", "登録日"])
        df['ファイル名'] = uploaded_file.name

        concat_df = pd.concat([concat_df, df])

    columns = ["商品名", "価格", "個数", "カテゴリー", "名称", "登録日", "ファイル名"]
    concat_df.columns = columns
    concat_df = concat_df.reset_index(drop=True)
    print(concat_df)
    output_file = os.path.join(output_folder, output_name)
    concat_df.to_csv(output_file, index=False, encoding='utf-8-sig')
    return output_file, concat_df
from fastapi import FastAPI, Depends, Request, HTTPException, Header,BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from sqlalchemy.orm import Session

from sql_app import schemas, models,crud
from sql_app.database import db_session, engine

import uvicorn
import json

from linebot import LineBotApi, WebhookHandler
from linebot.exceptions import InvalidSignatureError
from linebot.models import MessageEvent, TextMessage, FollowEvent,TextSendMessage,ImageSendMessage
from starlette.exceptions import HTTPException

import os
from os.path import join, dirname
from dotenv import load_dotenv 

models.Base.metadata.create_all(bind=engine)

app = FastAPI()

# dotenv_path = join(dirname(__file__), '.env')
# load_dotenv(dotenv_path)

# LINE Botのシークレットとアクセストークン
# LINE Bot APIとWebhookHandlerをインスタンス化します。
# LINE Bot APIは、LINEのメッセージを送受信するためのAPIを提供します。
# WebhookHandlerは、Webhookからのイベントを処理するためのクラスです。
# 環境変数から設定を読み込む
CHANNEL_SECRET = os.environ.get("CHA_SECRET", "default_secret")
CHANNEL_ACCESS_TOKEN = os.environ.get("CHA_ACCESS", "default_access")
CLIENT_ID = os.environ.get("CLIENT", "default_clientid") 

# LINE Bot APIを使うためのクライアントのインスタンス化
line_bot_api = LineBotApi(CHANNEL_ACCESS_TOKEN)
handler = WebhookHandler(CHANNEL_SECRET)

# image_url   = "https://i.imgur.com/7PeNPFY.jpg"  # このURLは実際の画像のURLに置き換える必要があります。
# preview_url = "https://i.imgur.com/7PeNPFY.jpg"  # プレビュー画像のURL。通常は元の画像と同じURLを使用することができます。

# FastAPIをインスタンス化
app = FastAPI()

headers = {
    'Authorization': f'Client-ID {CLIENT_ID}',
}

#通信設定
origins = [
    "*"
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

def get_db():
    db = db_session()
    try:
        yield db
    finally:
        db.close()

def get_db_session() -> Session:
    db = db_session()
    try:
        return db
    finally:
        db.close()

@app.get("/")
def index():
    return "Hello world"

###商品マスタ検索
@app.get("/search_product/{code}")
async def search(code:str, db: Session = Depends(get_db)):
    
    product_data = crud.get_product(db, code)
    print(product_data)

    if product_data:
        return product_data
    else:    
        return "null"

###購入明細の登録
@app.post("/buy_product/")
async def search(data:schemas.Transaction, db: Session = Depends(get_db)):
        TRD_ID = crud.create_transaction(db, data)
        for product in data.BUYPRODUCTS:
            print(product)
            for i in range(product.COUNT):
                promotion = db.query(models.Promotions).filter(models.Promotions.PRD_ID == product.PRD_ID).first()
                if promotion:
                    discount = promotion.DISCOUNT + product.PRICE * promotion.PERCENT
                    Transaction_detail = {
                        "TRD_ID" : TRD_ID,
                        "PRD_ID" : product.PRD_ID,
                        "PRD_CODE" : product.PRD_CODE,
                        "PRD_NAME" : product.NAME,
                        "PRD_PRICE" : product.PRICE,
                        "TAX_ID" : 1,
                        "PRM_ID" : promotion.PRM_ID,
                        "DISCOUNT" : discount
                    }
                else:
                    Transaction_detail = {
                        "TRD_ID" : TRD_ID,
                        "PRD_ID" : product.PRD_ID,
                        "PRD_CODE" : product.PRD_CODE,
                        "PRD_NAME" : product.NAME,
                        "PRD_PRICE" : product.PRICE,
                        "TAX_ID" : 1,
                        "PRM_ID" : None,  # プロモーションが存在しない場合はPRM_IDをNoneに設定
                        "DISCOUNT" : 0  # プロモーションが存在しない場合はDISCOUNTを0に設定
                    }
                crud.create_transaction_detail(db, Transaction_detail)

        TOTAL_AMT, TTL_AMT_EX_TAX = crud.update_transaction(db, TRD_ID)

        return True, TOTAL_AMT, TTL_AMT_EX_TAX

#Lineユーザーへの送信
@app.post("/promotion/{userid}/{image_url}")
def push_text(userid:str, image_url:str):
    #特定の１ユーザーに送る時はこちら。その他にも、マルチキャスト、ナローキャストがある。
    # line_bot_api.push_message(userid, TextSendMessage(text='test message from python to one user'))
    
    #画像の送信
    image_message = ImageSendMessage(original_content_url=image_url, preview_image_url=image_url)
    line_bot_api.push_message(userid, image_message)

    # with get_db_session() as db:
    #     users = db.query(models.User).all()
    #     for user in users:
    #         line_bot_api.push_message(user.LINE_ID, TextSendMessage(text='おいらは仁坊！'))



#Lineのイベント処理
@app.post("/callback")
async def callback(
    request: Request,
    background_tasks: BackgroundTasks,
    x_line_signature=Header(None),
    ):
    body = await request.body()

    try:
        background_tasks.add_task(
            handler.handle, body.decode("utf-8"), x_line_signature
        )
        
    except InvalidSignatureError:
        raise HTTPException(status_code=400, detail="Invalid signature")

    return "ok"

#登録・ブロック時の対応
@handler.add(FollowEvent)
def handle_follow(event):  # db 引数の型注釈を追加
    # Followイベントをハンドリングするコードをここに記述
    with get_db_session() as db:
        user_id = event.source.user_id
        user = models.User(
                    LINE_ID = user_id
                    )
        db.add(user)
        db.commit()
        db.refresh(user)
        print(event)

#メッセージ処理
@handler.add(MessageEvent)
def handle_message(event):
    if event.type != "message" or event.message.type != "text":
        return    
    message = TextMessage(text=event.message.text)
    line_bot_api.reply_message(event.reply_token, message)
    print(event)


# # 画像生成
# def generate_image_from_text(text: str, filename: str = "output.jpg"):
#     # Create a blank image
#     width, height = 400, 200
#     background_color = (255, 255, 255)
#     text_color = (0, 0, 0)
    
#     image = Image.new("RGB", (width, height), background_color)
#     draw = ImageDraw.Draw(image)

#     # You might need to adjust this font path or use a different font
#     font = ImageFont.truetype("arial.ttf", size=30)
#     text_width, text_height = draw.textsize(text, font=font)
#     text_position = ((width - text_width) / 2, (height - text_height) / 2)

#     draw.text(text_position, text, font=font, fill=text_color)

#     image.save(filename)

# # /callbackへのPOSTリクエストを処理するルートを定義
# @app.post("/callback/")
# async def callback(webhook_data: LineWebhook):
#     for event in webhook_data.events:
#         if event["type"] == "message":
#             # LINEサーバーから画像データをダウンロード
#             if event["message"]["type"] == "image":
#                 # LINEサーバーから画像データをダウンロード：download image data from line server
#                 message_content = line_bot_api.get_message_content(event["message"]["id"])
#                 # 画像データを一時ファイルに保存：save the image data to a temp file
#                 image_temp = tempfile.NamedTemporaryFile(delete=False)
#                 for chunk in message_content.iter_content():
#                     image_temp.write(chunk)
#                 image_temp.close()
#                 # # 画像からバーコードを読み取る：read the barcode from the image

#                 # ユーザーIDの取得
#                 user_id = event["source"]["userId"]
                
#             elif event["message"]["type"] == "text":
#                 text = event["message"]["text"]

                
#                 # Generate an image with the received text
#                 generate_image_from_text(text)
#                 # Now, upload this image to Imgur (or any other service) and get its URL
#                 with open('output.jpg', 'rb') as image_file:
#                     image_data = image_file.read()
#                     response = requests.post('https://api.imgur.com/3/image', headers=headers, data=image_data)
#                 data = response.json()
#                 image_url = data['data']['link']

#                 # Create an ImageSendMessage with the uploaded image URL
#                 image_message = ImageSendMessage(original_content_url=image_url, preview_image_url=image_url)

#                 # Send the image back to the user
#                 line_bot_api.reply_message(event["replyToken"], image_message)
import json
from datetime import date

# 擴充 25+ 間新北市代表性幼兒園示範資料
NEW_DEMO = {
    "_meta": {
        "notice": "本檔為『公開輿情觀測』的示範資料（DEMO），涵蓋 Google 評論／Facebook／Instagram／部落格／公開論壇等多來源樣本，用於展示時間序列分級、輿情關注指數與依據呈現方式，非真實輿情，亦非對任何機構之事實認定。新聞由系統即時蒐集公開新聞報導；上述社群與評論來源於正式版需透過各平台官方 API 授權接入，且不蒐集需登入才可見之內容。",
        "compliance": "僅示範公開來源；每則保留原始來源型別、發布時間與可回溯連結，家長可回原文自行判斷。新聞為即時蒐集，已盡力以園名與行政區精確比對。支援以機構代碼或園所名稱索引。",
        "reference_date": "2026-09-12",
        "window_days": 365
    },
    "institutions": {
        "74670790-1bf5-4d0e-aee3-12b41d4213ca": {
            "park_name": "新北市私立嘉盛幼兒園",
            "is_demo": True,
            "items": [
                {
                    "source_type": "review",
                    "source_name": "Google 評論（示範）",
                    "title": "環境還不錯，老師親切",
                    "excerpt": "校園乾淨、老師都很親切，孩子適應得不錯。",
                    "url": "https://www.google.com/maps/search/嘉盛幼兒園",
                    "published": "2025-12-15"
                },
                {
                    "source_type": "review",
                    "source_name": "Google 評論（示範）",
                    "title": "收費項目希望更透明",
                    "excerpt": "覺得部分代辦費項目說明可以再清楚一點，跟園方反映後有回覆。",
                    "url": "https://www.google.com/maps/search/嘉盛幼兒園",
                    "published": "2026-06-10"
                },
                {
                    "source_type": "forum",
                    "source_name": "公開論壇（示範）",
                    "title": "請問這間收費合理嗎",
                    "excerpt": "最近在看這間，想問其他家長對收費與退費的看法，會不會偏貴。",
                    "url": "https://www.mobile01.com/topicdetail.php",
                    "published": "2026-07-08"
                },
                {
                    "source_type": "facebook",
                    "source_name": "Facebook 公開社團（示範）",
                    "title": "板橋育兒交流：師資異動討論",
                    "excerpt": "公開社團有家長討論這學期師資異動的情形，希望園方多說明。",
                    "url": "https://www.facebook.com/",
                    "published": "2026-07-25"
                },
                {
                    "source_type": "review",
                    "source_name": "Google 評論（示範）",
                    "title": "退費流程有點複雜",
                    "excerpt": "辦理退費時覺得流程較繁瑣，希望能更順暢，其他方面尚可。",
                    "url": "https://www.google.com/maps/search/嘉盛幼兒園",
                    "published": "2026-08-06"
                },
                {
                    "source_type": "forum",
                    "source_name": "公開論壇（示範）",
                    "title": "代辦費討論串",
                    "excerpt": "有家長分享代辦費的疑問，串上不少人回覆自身經驗，意見兩極。",
                    "url": "https://www.mobile01.com/topicdetail.php",
                    "published": "2026-08-18"
                },
                {
                    "source_type": "instagram",
                    "source_name": "Instagram 公開貼文（示範）",
                    "title": "分享園所活動花絮",
                    "excerpt": "帶孩子參加園方活動，現場布置很用心，拍了幾張分享。",
                    "url": "https://www.instagram.com/",
                    "published": "2026-08-24"
                },
                {
                    "source_type": "blog",
                    "source_name": "育兒部落格（示範）",
                    "title": "選幼兒園觀察：收費透明與師資穩定",
                    "excerpt": "整理幾個評估面向，收費透明度與師資穩定度是我最在意的兩點。",
                    "url": "https://example-parenting-blog.tw/post/kindergarten",
                    "published": "2026-08-29"
                }
            ]
        },
        "02d6d62d-c603-40fb-9216-e32b0dbc529b": {
            "park_name": "新北市私立雙成幼兒園",
            "is_demo": True,
            "items": [
                {
                    "source_type": "review",
                    "source_name": "Google 評論（示範）",
                    "title": "老師很用心，孩子喜歡上學",
                    "excerpt": "老師認真又貼心，孩子每天都很期待上學，環境也乾淨整潔。",
                    "url": "https://www.google.com/maps/search/雙成幼兒園",
                    "published": "2026-05-20"
                },
                {
                    "source_type": "review",
                    "source_name": "Google 評論（示範）",
                    "title": "整體滿意，課程豐富",
                    "excerpt": "課程安排豐富，行政溝通順暢，整體很滿意，推薦。",
                    "url": "https://www.google.com/maps/search/雙成幼兒園",
                    "published": "2026-08-04"
                },
                {
                    "source_type": "facebook",
                    "source_name": "Facebook 公開貼文（示範）",
                    "title": "參觀心得分享",
                    "excerpt": "參觀時覺得接待老師很有耐心，說明很詳細，印象良好。",
                    "url": "https://www.facebook.com/",
                    "published": "2026-08-15"
                }
            ]
        },
        "R0132": {
            "park_name": "新北市私立嘉盛幼兒園",
            "is_demo": True,
            "items": [
                {
                    "source_type": "review",
                    "source_name": "Google 評論（示範）",
                    "title": "環境還不錯，老師親切",
                    "excerpt": "校園乾淨、老師都很親切，孩子適應得不錯。",
                    "url": "https://www.google.com/maps/search/嘉盛幼兒園",
                    "published": "2025-12-15"
                },
                {
                    "source_type": "review",
                    "source_name": "Google 評論（示範）",
                    "title": "收費項目希望更透明",
                    "excerpt": "覺得部分代辦費項目說明可以再清楚一點，跟園方反映後有回覆。",
                    "url": "https://www.google.com/maps/search/嘉盛幼兒園",
                    "published": "2026-06-10"
                },
                {
                    "source_type": "forum",
                    "source_name": "公開論壇（示範）",
                    "title": "請問這間收費合理嗎",
                    "excerpt": "最近在看這間，想問其他家長對收費與退費的看法，會不會偏貴。",
                    "url": "https://www.mobile01.com/topicdetail.php",
                    "published": "2026-07-08"
                },
                {
                    "source_type": "facebook",
                    "source_name": "Facebook 公開社團（示範）",
                    "title": "板橋育兒交流：師資異動討論",
                    "excerpt": "公開社團有家長討論這學期師資異動的情形，希望園方多說明。",
                    "url": "https://www.facebook.com/",
                    "published": "2026-07-25"
                },
                {
                    "source_type": "review",
                    "source_name": "Google 評論（示範）",
                    "title": "退費流程有點複雜",
                    "excerpt": "辦理退費時覺得流程較繁瑣，希望能更順暢，其他方面尚可。",
                    "url": "https://www.google.com/maps/search/嘉盛幼兒園",
                    "published": "2026-08-06"
                },
                {
                    "source_type": "forum",
                    "source_name": "公開論壇（示範）",
                    "title": "代辦費討論串",
                    "excerpt": "有家長分享代辦費的疑問，串上不少人回覆自身經驗，意見兩極。",
                    "url": "https://www.mobile01.com/topicdetail.php",
                    "published": "2026-08-18"
                }
            ]
        },
        "R0072": {
            "park_name": "新北市私立雙成幼兒園",
            "is_demo": True,
            "items": [
                {
                    "source_type": "review",
                    "source_name": "Google 評論（示範）",
                    "title": "老師很用心，孩子喜歡上學",
                    "excerpt": "老師認真又貼心，孩子每天都很期待上學，環境也乾淨整潔。",
                    "url": "https://www.google.com/maps/search/雙成幼兒園",
                    "published": "2026-05-20"
                },
                {
                    "source_type": "review",
                    "source_name": "Google 評論（示範）",
                    "title": "整體滿意，課程豐富",
                    "excerpt": "課程安排豐富，行政溝通順暢，整體很滿意，推薦。",
                    "url": "https://www.google.com/maps/search/雙成幼兒園",
                    "published": "2026-08-04"
                },
                {
                    "source_type": "facebook",
                    "source_name": "Facebook 公開貼文（示範）",
                    "title": "參觀心得分享",
                    "excerpt": "參觀時覺得接待老師很有耐心，說明很詳細，印象良好。",
                    "url": "https://www.facebook.com/",
                    "published": "2026-08-15"
                }
            ]
        },
        "R0005": {
            "park_name": "新北市私立吉的堡南雅幼兒園",
            "is_demo": True,
            "items": [
                {
                    "source_type": "review",
                    "source_name": "Google 評論（示範）",
                    "title": "美語互動活潑，孩子學得開心",
                    "excerpt": "美語主題課程很有趣，老師親切活潑，小朋友回家會主動唱英文童謠。",
                    "url": "https://www.google.com/maps/search/吉的堡南雅幼兒園",
                    "published": "2026-05-18"
                },
                {
                    "source_type": "forum",
                    "source_name": "公開論壇（示範）",
                    "title": "板橋南雅周邊幼兒園詢問",
                    "excerpt": "想請教南雅吉的堡的戶外活動空間與接送動線，整體師資穩定嗎？",
                    "url": "https://www.mobile01.com/topicdetail.php",
                    "published": "2026-07-12"
                },
                {
                    "source_type": "review",
                    "source_name": "Google 評論（示範）",
                    "title": "門禁管理很確實",
                    "excerpt": "接送時間門禁管制嚴格，老師都會核對家長接送卡，家長感覺滿放心的。",
                    "url": "https://www.google.com/maps/search/吉的堡南雅幼兒園",
                    "published": "2026-08-20"
                }
            ]
        },
        "R0197": {
            "park_name": "新北市私立吉的堡英資幼兒園",
            "is_demo": True,
            "items": [
                {
                    "source_type": "review",
                    "source_name": "Google 評論（示範）",
                    "title": "幼幼班老師極具耐心",
                    "excerpt": "幼幼班剛入學哭得很厲害，班導師很有耐心抱著安撫，兩週就適應良好。",
                    "url": "https://www.google.com/maps/search/吉的堡英資幼兒園",
                    "published": "2026-04-15"
                },
                {
                    "source_type": "facebook",
                    "source_name": "Facebook 公開貼文（示範）",
                    "title": "三重育兒社團參觀分享",
                    "excerpt": "參觀英資園的心得：教室採光充足且通風良好，教具很整潔。",
                    "url": "https://www.facebook.com/",
                    "published": "2026-06-28"
                },
                {
                    "source_type": "review",
                    "source_name": "Google 評論（示範）",
                    "title": "行政回覆效率高",
                    "excerpt": "課後延托與行政事務詢問，園方回覆很迅速清楚，整體體驗良好。",
                    "url": "https://www.google.com/maps/search/吉的堡英資幼兒園",
                    "published": "2026-08-05"
                }
            ]
        },
        "R0377": {
            "park_name": "新北市私立何嘉仁得和幼兒園",
            "is_demo": True,
            "items": [
                {
                    "source_type": "review",
                    "source_name": "Google 評論（示範）",
                    "title": "外師發音標準，孩子喜歡表達",
                    "excerpt": "外籍老師很活潑，中師在旁輔助，孩子在英語環境中很自然敢開口。",
                    "url": "https://www.google.com/maps/search/何嘉仁得和幼兒園",
                    "published": "2026-04-20"
                },
                {
                    "source_type": "forum",
                    "source_name": "公開論壇（示範）",
                    "title": "永和得和幼兒園收費與教學請益",
                    "excerpt": "想詢問何嘉仁得和分校的教材費與餐點水準，老師流動率高嗎？",
                    "url": "https://www.mobile01.com/topicdetail.php",
                    "published": "2026-07-06"
                },
                {
                    "source_type": "review",
                    "source_name": "Google 評論（示範）",
                    "title": "聯絡簿記錄用心",
                    "excerpt": "每天在校生活與飲食作息都交代得很具體，親師溝通很透明。",
                    "url": "https://www.google.com/maps/search/何嘉仁得和幼兒園",
                    "published": "2026-08-14"
                }
            ]
        },
        "R0479": {
            "park_name": "新北市私立何嘉仁幼兒園",
            "is_demo": True,
            "items": [
                {
                    "source_type": "review",
                    "source_name": "Google 評論（示範）",
                    "title": "主題教學豐富有趣",
                    "excerpt": "配合節慶和科學探索設計單元主題，孩子每天上學都很有收穫。",
                    "url": "https://www.google.com/maps/search/新莊何嘉仁幼兒園",
                    "published": "2026-05-10"
                },
                {
                    "source_type": "review",
                    "source_name": "Google 評論（示範）",
                    "title": "餐點菜單每週公告",
                    "excerpt": "每週菜單營養很均衡，遇到過敏食材也會特別幫小孩替換，值得推薦。",
                    "url": "https://www.google.com/maps/search/新莊何嘉仁幼兒園",
                    "published": "2026-07-16"
                }
            ]
        },
        "R0390": {
            "park_name": "新北市私立幼愛幼兒園",
            "is_demo": True,
            "items": [
                {
                    "source_type": "review",
                    "source_name": "Google 評論（示範）",
                    "title": "新莊在地老牌園所，師資資深穩定",
                    "excerpt": "幾位資深老師在新莊教很多年了，很有耐心也很懂幼兒心理，送這裡很放心。",
                    "url": "https://www.google.com/maps/search/新莊幼愛幼兒園",
                    "published": "2026-03-25"
                },
                {
                    "source_type": "review",
                    "source_name": "Google 評論（示範）",
                    "title": "有綠蔭戶外活動空間",
                    "excerpt": "院子裡有大樹跟戶外遊樂設施，每天都有充足戶外跑跳曬太陽的時間。",
                    "url": "https://www.google.com/maps/search/新莊幼愛幼兒園",
                    "published": "2026-05-30"
                },
                {
                    "source_type": "forum",
                    "source_name": "公開論壇（示範）",
                    "title": "新莊幸福商圈幼愛幼兒園請益",
                    "excerpt": "請問幼愛幼兒園的收費跟作息規劃？參觀過覺得老師很親切樸實。",
                    "url": "https://www.mobile01.com/topicdetail.php",
                    "published": "2026-07-22"
                },
                {
                    "source_type": "review",
                    "source_name": "Google 評論（示範）",
                    "title": "收費實在，沒有繁雜額外自費",
                    "excerpt": "收費非常公道透明，不會一直推銷才藝課，是腳踏實地的好學校。",
                    "url": "https://www.google.com/maps/search/新莊幼愛幼兒園",
                    "published": "2026-08-18"
                }
            ]
        },
        "R0406": {
            "park_name": "新北市私立育全幼兒園",
            "is_demo": True,
            "items": [
                {
                    "source_type": "review",
                    "source_name": "Google 評論（示範）",
                    "title": "校園腹地廣大，活動量充足",
                    "excerpt": "在新莊少見的大型活動空間，體能課有專業教練帶領，孩子體能大有進步。",
                    "url": "https://www.google.com/maps/search/新莊育全幼兒園",
                    "published": "2026-04-18"
                },
                {
                    "source_type": "review",
                    "source_name": "Google 評論（示範）",
                    "title": "節慶大型活動很精采",
                    "excerpt": "萬聖節踩街與聖誕晚會辦得很盛大，老師們道具準備超級用心。",
                    "url": "https://www.google.com/maps/search/新莊育全幼兒園",
                    "published": "2026-06-12"
                },
                {
                    "source_type": "forum",
                    "source_name": "公開論壇（示範）",
                    "title": "新莊育全大班幼小銜接準備詢問",
                    "excerpt": "想請問育全在大班是否有銜接國小的生活自理與拼音引導？",
                    "url": "https://www.mobile01.com/topicdetail.php",
                    "published": "2026-08-01"
                }
            ]
        },
        "P0576": {
            "park_name": "新北市私立育全保安幼兒園",
            "is_demo": True,
            "items": [
                {
                    "source_type": "review",
                    "source_name": "Google 評論（示範）",
                    "title": "生活自理訓練有成",
                    "excerpt": "孩子進去讀幾個月後學會自己收拾書包玩具，生活習慣進步很多。",
                    "url": "https://www.google.com/maps/search/育全保安幼兒園",
                    "published": "2026-05-15"
                },
                {
                    "source_type": "review",
                    "source_name": "Google 評論（示範）",
                    "title": "接送時段保安街車流較多",
                    "excerpt": "放學時段門口車位較難停，希望家長們配合依序接送，園方導護很盡責。",
                    "url": "https://www.google.com/maps/search/育全保安幼兒園",
                    "published": "2026-07-11"
                }
            ]
        },
        "P0149": {
            "park_name": "新北市私立欣勵德幼兒園",
            "is_demo": True,
            "items": [
                {
                    "source_type": "review",
                    "source_name": "Google 評論（示範）",
                    "title": "老師親切有愛心",
                    "excerpt": "班級人數適中，老師很有同理心，孩子每天都很開心去學校。",
                    "url": "https://www.google.com/maps/search/欣勵德幼兒園",
                    "published": "2026-05-04"
                },
                {
                    "source_type": "forum",
                    "source_name": "公開論壇（示範）",
                    "title": "板橋欣勵德幼兒園參訪討論",
                    "excerpt": "想請問有讀過欣勵德的家長，餐點多樣性與退費規範如何？",
                    "url": "https://www.mobile01.com/topicdetail.php",
                    "published": "2026-07-03"
                }
            ]
        },
        "P0018": {
            "park_name": "新北市私立和平幼兒園",
            "is_demo": True,
            "items": [
                {
                    "source_type": "review",
                    "source_name": "Google 評論（示範）",
                    "title": "收費清楚，環境整潔",
                    "excerpt": "收費明細一清二楚，每週都會看到固定紫外線消毒，環境保持很乾淨。",
                    "url": "https://www.google.com/maps/search/板橋和平幼兒園",
                    "published": "2026-05-22"
                },
                {
                    "source_type": "review",
                    "source_name": "Google 評論（示範）",
                    "title": "親師溝通很及時",
                    "excerpt": "孩子在校有任何碰撞小狀況，老師第一時間都會主動電話向家長回報說明。",
                    "url": "https://www.google.com/maps/search/板橋和平幼兒園",
                    "published": "2026-07-30"
                }
            ]
        },
        "R0105": {
            "park_name": "新北市立板橋幼兒園和平分班",
            "is_demo": True,
            "items": [
                {
                    "source_type": "review",
                    "source_name": "Google 評論（示範）",
                    "title": "公幼體制師資專業規範",
                    "excerpt": "公立幼兒園師生比嚴格落實，教保活動依綱要落實，完全不強推任何自費教材。",
                    "url": "https://www.google.com/maps/search/板橋幼兒園和平分班",
                    "published": "2026-03-15"
                },
                {
                    "source_type": "forum",
                    "source_name": "公開論壇（示範）",
                    "title": "板橋公幼抽籤與分班心得",
                    "excerpt": "板橋和平分班的師資與戶外活動評價很不錯，抽到的家長滿推薦的。",
                    "url": "https://www.mobile01.com/topicdetail.php",
                    "published": "2026-06-20"
                }
            ]
        },
        "R0000": {
            "park_name": "新北市私立悅淨幼兒園",
            "is_demo": True,
            "items": [
                {
                    "source_type": "review",
                    "source_name": "Google 評論（示範）",
                    "title": "準公共平價優質選擇",
                    "excerpt": "加入準公共減輕很多經濟負擔，老師教學細心，孩子每天都很開心。",
                    "url": "https://www.google.com/maps/search/悅淨幼兒園",
                    "published": "2026-05-11"
                },
                {
                    "source_type": "review",
                    "source_name": "Google 評論（示範）",
                    "title": "小班制照顧周全",
                    "excerpt": "每班人數控制良好，吃飯與午睡作息老師都很悉心照顧，值得肯定。",
                    "url": "https://www.google.com/maps/search/悅淨幼兒園",
                    "published": "2026-07-26"
                }
            ]
        },
        "R0236": {
            "park_name": "新北市私立安安堡幼兒園",
            "is_demo": True,
            "items": [
                {
                    "source_type": "review",
                    "source_name": "Google 評論（示範）",
                    "title": "蒙特梭利教學環境豐富",
                    "excerpt": "教具種類豐富齊全，老師引導孩子自我探索，專注力跟定性都有提升。",
                    "url": "https://www.google.com/maps/search/安安堡幼兒園",
                    "published": "2026-04-26"
                },
                {
                    "source_type": "facebook",
                    "source_name": "Facebook 公開貼文（示範）",
                    "title": "中和蒙氏幼兒園參訪筆記",
                    "excerpt": "參觀安安堡的教室氛圍安靜專注，老師講話語氣很柔和，感覺很舒服。",
                    "url": "https://www.facebook.com/",
                    "published": "2026-07-09"
                }
            ]
        },
        "R0382": {
            "park_name": "新北市私立太陽花幼兒園",
            "is_demo": True,
            "items": [
                {
                    "source_type": "review",
                    "source_name": "Google 評論（示範）",
                    "title": "老師很有朝氣，校門管制嚴謹",
                    "excerpt": "門口警衛負責核對身分，老師每天在門口精神奕奕迎接小朋友，氛圍溫馨。",
                    "url": "https://www.google.com/maps/search/新莊太陽花幼兒園",
                    "published": "2026-05-02"
                },
                {
                    "source_type": "review",
                    "source_name": "Google 評論（示範）",
                    "title": "每月水果日推廣健康飲食",
                    "excerpt": "園所注重幼兒營養，少油少鹽，小朋友原本挑食現在都會主動吃蔬菜了。",
                    "url": "https://www.google.com/maps/search/新莊太陽花幼兒園",
                    "published": "2026-07-21"
                }
            ]
        },
        "R0152": {
            "park_name": "新北市私立育林幼兒園",
            "is_demo": True,
            "items": [
                {
                    "source_type": "review",
                    "source_name": "Google 評論（示範）",
                    "title": "重視閱讀與生活習慣養成",
                    "excerpt": "每週五借閱繪本回家共讀，孩子建立很好的閱讀習慣，老師常給鼓勵。",
                    "url": "https://www.google.com/maps/search/三重育林幼兒園",
                    "published": "2026-04-30"
                },
                {
                    "source_type": "forum",
                    "source_name": "公開論壇（示範）",
                    "title": "三重育林幼兒園評價交流",
                    "excerpt": "想請教三重育林幼兒園的名額情況與收費明細，整體風評如何？",
                    "url": "https://www.mobile01.com/topicdetail.php",
                    "published": "2026-06-25"
                }
            ]
        },
        "R0487": {
            "park_name": "新北市私立劍聲幼兒園",
            "is_demo": True,
            "items": [
                {
                    "source_type": "review",
                    "source_name": "Google 評論（示範）",
                    "title": "感覺統合與感官操作教具多",
                    "excerpt": "教材多元，引導孩子動手做，老師引導耐心，小朋友每天都充滿好奇心。",
                    "url": "https://www.google.com/maps/search/新店劍聲幼兒園",
                    "published": "2026-05-17"
                },
                {
                    "source_type": "review",
                    "source_name": "Google 評論（示範）",
                    "title": "專屬戶外活動區活動量夠",
                    "excerpt": "新店少數擁有寬敞戶外專屬遊戲區的幼兒園，活動量很充足。",
                    "url": "https://www.google.com/maps/search/新店劍聲幼兒園",
                    "published": "2026-07-13"
                }
            ]
        },
        "R0733": {
            "park_name": "新北市私立華慶幼兒園",
            "is_demo": True,
            "items": [
                {
                    "source_type": "review",
                    "source_name": "Google 評論（示範）",
                    "title": "準公幼收費平實，老師認真",
                    "excerpt": "家長群組溝通即時，老師回饋認真，準公幼費用減輕不少家庭負擔。",
                    "url": "https://www.google.com/maps/search/汐止華慶幼兒園",
                    "published": "2026-05-09"
                },
                {
                    "source_type": "review",
                    "source_name": "Google 評論（示範）",
                    "title": "雨天有大型室內活動空間",
                    "excerpt": "汐止常下雨，好在園內有很大的室內體能空間，雨天孩子照樣能開展運動。",
                    "url": "https://www.google.com/maps/search/汐止華慶幼兒園",
                    "published": "2026-07-02"
                }
            ]
        },
        "R0987": {
            "park_name": "新北市私立林口愛丁堡幼兒園",
            "is_demo": True,
            "items": [
                {
                    "source_type": "review",
                    "source_name": "Google 評論（示範）",
                    "title": "校園寬敞採光充足，草地運動場",
                    "excerpt": "林口校舍環境優質，有大片草坪跟戶外運動設施，孩子運動視野極佳。",
                    "url": "https://www.google.com/maps/search/林口愛丁堡幼兒園",
                    "published": "2026-04-14"
                },
                {
                    "source_type": "forum",
                    "source_name": "公開論壇（示範）",
                    "title": "林口愛丁堡雙語教學與校車接送",
                    "excerpt": "想了解愛丁堡幼兒園外師穩定度與校車接送路線，希望在讀家長分享。",
                    "url": "https://www.mobile01.com/topicdetail.php",
                    "published": "2026-07-20"
                }
            ]
        },
        "R0809": {
            "park_name": "新北市私立華德幼兒園",
            "is_demo": True,
            "items": [
                {
                    "source_type": "review",
                    "source_name": "Google 評論（示範）",
                    "title": "老師耐心指導常規",
                    "excerpt": "老師很有耐心指導日常常規，環境乾淨衛生，定期聘請專業消毒清潔。",
                    "url": "https://www.google.com/maps/search/土城華德幼兒園",
                    "published": "2026-05-16"
                },
                {
                    "source_type": "forum",
                    "source_name": "公開論壇（示範）",
                    "title": "土城中央路周邊幼兒園推薦請益",
                    "excerpt": "想請教土城華德幼兒園參觀評價，收費標準與師生流動情況。",
                    "url": "https://www.mobile01.com/topicdetail.php",
                    "published": "2026-08-11"
                }
            ]
        },
        "R0873": {
            "park_name": "新北市私立長興幼兒園",
            "is_demo": True,
            "items": [
                {
                    "source_type": "review",
                    "source_name": "Google 評論（示範）",
                    "title": "老師教學具熱忱",
                    "excerpt": "聯絡簿寫得很詳細，老師對小朋友非常關心，安全防護邊角都有做防撞條。",
                    "url": "https://www.google.com/maps/search/蘆洲長興幼兒園",
                    "published": "2026-04-22"
                },
                {
                    "source_type": "review",
                    "source_name": "Google 評論（示範）",
                    "title": "行政溝通良好順暢",
                    "excerpt": "園方行政人員客氣好溝通，放學接送管制秩序井然。",
                    "url": "https://www.google.com/maps/search/蘆洲長興幼兒園",
                    "published": "2026-07-15"
                }
            ]
        },
        "R0566": {
            "park_name": "新北市私立建丞幼兒園",
            "is_demo": True,
            "items": [
                {
                    "source_type": "review",
                    "source_name": "Google 評論（示範）",
                    "title": "樹林在地資深口碑園所",
                    "excerpt": "資深老師很了解幼兒各年齡層需求，點心料理清淡營養，小朋友很愛吃。",
                    "url": "https://www.google.com/maps/search/樹林建丞幼兒園",
                    "published": "2026-05-06"
                },
                {
                    "source_type": "forum",
                    "source_name": "公開論壇（示範）",
                    "title": "樹林建丞幼兒園課後才藝分享",
                    "excerpt": "有讀建丞的家長可以分享課後才藝與延托時段規劃嗎？",
                    "url": "https://www.mobile01.com/topicdetail.php",
                    "published": "2026-08-12"
                }
            ]
        },
        "R0611": {
            "park_name": "新北市私立宏修幼兒園",
            "is_demo": True,
            "items": [
                {
                    "source_type": "review",
                    "source_name": "Google 評論（示範）",
                    "title": "準公幼收費平易近人，環境純樸清幽",
                    "excerpt": "周邊環境安靜單純，園長跟老師都很誠懇，收費完全照準公共標準走。",
                    "url": "https://www.google.com/maps/search/鶯歌宏修幼兒園",
                    "published": "2026-05-24"
                },
                {
                    "source_type": "review",
                    "source_name": "Google 評論（示範）",
                    "title": "戶外自然空間適中",
                    "excerpt": "有小花園可以觀察植物生態，老師常常帶小朋友在戶外進行自然探索。",
                    "url": "https://www.google.com/maps/search/鶯歌宏修幼兒園",
                    "published": "2026-07-18"
                }
            ]
        },
        "P0285": {
            "park_name": "新北市私立興南幼兒園",
            "is_demo": True,
            "items": [
                {
                    "source_type": "review",
                    "source_name": "Google 評論（示範）",
                    "title": "活動豐富，接送車位需注意",
                    "excerpt": "校內活動規劃多元，不過接送尖峰時段周邊車流量較大，需注意違停狀況。",
                    "url": "https://www.google.com/maps/search/中和興南幼兒園",
                    "published": "2026-06-11"
                },
                {
                    "source_type": "forum",
                    "source_name": "公開論壇（示範）",
                    "title": "中和興南幼兒園行政溝通心得",
                    "excerpt": "有家長在論壇討論近期行政溝通與活動通知時程，希望時效更早一些。",
                    "url": "https://www.mobile01.com/topicdetail.php",
                    "published": "2026-07-25"
                }
            ]
        },
        "P0895": {
            "park_name": "新北市私立蘆洲來來幼兒園",
            "is_demo": True,
            "items": [
                {
                    "source_type": "review",
                    "source_name": "Google 評論（示範）",
                    "title": "老師教學認真，常規嚴謹",
                    "excerpt": "老師教學很有條理，生活常規要求較明確，孩子自理能力進步快。",
                    "url": "https://www.google.com/maps/search/蘆洲來來幼兒園",
                    "published": "2026-05-19"
                },
                {
                    "source_type": "forum",
                    "source_name": "公開論壇（示範）",
                    "title": "蘆洲來來幼兒園師生比與教學交流",
                    "excerpt": "想了解來來幼兒園師生比配置與實際課堂作息情況。",
                    "url": "https://www.mobile01.com/topicdetail.php",
                    "published": "2026-07-16"
                }
            ]
        },
        "P0756": {
            "park_name": "新北市私立安格幼兒園",
            "is_demo": True,
            "items": [
                {
                    "source_type": "review",
                    "source_name": "Google 評論（示範）",
                    "title": "雙語氣氛熱絡，外師互動佳",
                    "excerpt": "英語課程設計生動，孩子在校很敢開口，行政溝通算暢通。",
                    "url": "https://www.google.com/maps/search/汐止安格幼兒園",
                    "published": "2026-05-28"
                },
                {
                    "source_type": "forum",
                    "source_name": "公開論壇（示範）",
                    "title": "汐止安格幼兒園課後活動與收費",
                    "excerpt": "請益安格幼兒園課堂活動安排與教材收費相關反饋。",
                    "url": "https://www.mobile01.com/topicdetail.php",
                    "published": "2026-08-09"
                }
            ]
        },
        "P0648": {
            "park_name": "新北市私立文化幼兒園",
            "is_demo": True,
            "items": [
                {
                    "source_type": "review",
                    "source_name": "Google 評論（示範）",
                    "title": "校舍寬敞，老師具親和力",
                    "excerpt": "鄰近三峽老街周邊，校園空間算大，老師很有親和力，孩子每天笑咪咪出門。",
                    "url": "https://www.google.com/maps/search/三峽文化幼兒園",
                    "published": "2026-05-15"
                },
                {
                    "source_type": "forum",
                    "source_name": "公開論壇（示範）",
                    "title": "三峽文化幼兒園教學特色討論",
                    "excerpt": "想請問文化幼兒園的蒙氏與主題操作安排，歡迎家長分享。",
                    "url": "https://www.mobile01.com/topicdetail.php",
                    "published": "2026-07-28"
                }
            ]
        }
    }
}

if __name__ == "__main__":
    with open("public/data/sentiment_demo.json", "w", encoding="utf-8") as f:
        json.dump(NEW_DEMO, f, ensure_ascii=False, indent=2)
    print("Successfully expanded sentiment_demo.json. Total institutions:", len(NEW_DEMO["institutions"]))

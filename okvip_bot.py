import os
import json
import time
import asyncio
from aiohttp import web, ClientSession
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.types import (
    InlineKeyboardMarkup,
    InlineKeyboardButton,
    ReplyKeyboardMarkup,
    KeyboardButton,
    BotCommand,
    BotCommandScopeDefault,
    BotCommandScopeChat,
)

BOT_TOKEN = "{BOT_TOKEN_MOI}"
ADMIN_ID = 5412396531

BANK_STK = "175198"
BANK_BANK = "MBBANK"
BANK_NAME = "VU DUNG ANH"

SEPAY_PATH = "/sepay-payment"
WEBHOOK_PORT = 8080
FORWARD_WEBHOOK_URL = "https://charlee-emulative-nonpermissibly.ngrok-free.dev/sepay-payment"

DB_FILE = "db.json"
PRICE_PER_POINT = 500  # 100 điểm = 50.000đ


def ensure_db():
    if not os.path.exists(DB_FILE):
        with open(DB_FILE, "w", encoding="utf-8") as f:
            json.dump({"users": {}, "kho": [], "don": [], "nap": []}, f, indent=4)


def load_db():
    ensure_db()
    with open(DB_FILE, "r", encoding="utf-8") as f:
        return json.load(f)


def save_db(data):
    with open(DB_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=4)


def get_user(uid):
    db = load_db()
    if str(uid) not in db["users"]:
        db["users"][str(uid)] = {
            "name": "",
            "balance": 0,
            "total_nap": 0,
            "total_dung": 0,
        }
        save_db(db)
    return db["users"][str(uid)]


def update_user(uid, key, value):
    db = load_db()
    if str(uid) not in db["users"]:
        get_user(uid)
        db = load_db()
    db["users"][str(uid)][key] = value
    save_db(db)


def get_kho_available():
    return [k for k in load_db()["kho"] if not k.get("sold")]


def mark_kho_sold(kho_id):
    db = load_db()
    for i in db["kho"]:
        if i["id"] == kho_id:
            i["sold"] = True
    save_db(db)


def add_don(user_id, kho_id, so_diem, so_tien, game, tk_game, so4):
    db = load_db()
    don_id = int(time.time() * 1000)
    db["don"].append(
        {
            "id": don_id,
            "user_id": user_id,
            "kho_id": kho_id,
            "so_diem": so_diem,
            "so_tien": so_tien,
            "game": game,
            "tk_game": tk_game,
            "so4": so4,
            "status": 0,
            "time": time.time(),
        }
    )
    save_db(db)
    return don_id


bot = Bot(BOT_TOKEN)
dp = Dispatcher()
pending_step: dict[int, tuple[str, object]] = {}
admin_pending: dict[int, str] = {}


def calc_price_from_points(points: int) -> int:
    return points * PRICE_PER_POINT


def create_kho_entry(so_diem: int, ds_game: str, ghichu: str) -> dict:
    return {
        "id": int(time.time() * 1000),
        "so_diem": so_diem,
        "gia": calc_price_from_points(so_diem),
        "ds_game": ds_game,
        "ghichu": ghichu,
        "sold": False,
    }


USER_REPLY_KB = ReplyKeyboardMarkup(
    keyboard=[
        [
            KeyboardButton(text="🛒 Mua Điểm"),
            KeyboardButton(text="💳 Nạp Tiền"),
        ],
        [
            KeyboardButton(text="📚 Lịch Sử"),
            KeyboardButton(text="👤 Hồ Sơ"),
        ],
        [KeyboardButton(text="📨 Hỗ Trợ")],
    ],
    resize_keyboard=True,
)


USER_INLINE_KB = InlineKeyboardMarkup(
    inline_keyboard=[
        [InlineKeyboardButton(text="🛒 Mua Điểm", callback_data="muadiem")],
        [InlineKeyboardButton(text="💳 Nạp Tiền", callback_data="naptien")],
        [InlineKeyboardButton(text="📚 Lịch Sử", callback_data="lichsu")],
        [InlineKeyboardButton(text="👤 Hồ Sơ", callback_data="hoso")],
        [InlineKeyboardButton(text="📨 Hỗ Trợ", callback_data="hotro")],
    ]
)


ADMIN_MENU_KB = InlineKeyboardMarkup(
    inline_keyboard=[
        [InlineKeyboardButton(text="📊 Thống kê", callback_data="admin_stats")],
        [InlineKeyboardButton(text="📦 Đơn chờ", callback_data="admin_pending")],
        [InlineKeyboardButton(text="➕ Thêm điểm", callback_data="admin_add_kho")],
        [InlineKeyboardButton(text="🗑 Xóa điểm", callback_data="admin_remove_kho")],
        [InlineKeyboardButton(text="↩️ Menu người dùng", callback_data="admin_back_user")],
    ]
)


async def send_with_context(target: types.CallbackQuery | types.Message, text: str, **kwargs):
    if isinstance(target, types.CallbackQuery):
        await target.answer()
        await target.message.edit_text(text, **kwargs)
    else:
        await target.answer(text, **kwargs)


def build_user_menu_text(user: types.User) -> str:
    return (
        f"👋 Xin chào **{user.first_name}**\n"
        f"ID: `{user.id}`\n"
        "Chọn tính năng bên dưới để tiếp tục."
    )


async def send_user_welcome(msg: types.Message):
    get_user(msg.from_user.id)
    text = build_user_menu_text(msg.from_user)
    await msg.answer(text, reply_markup=USER_INLINE_KB, parse_mode="Markdown")
    await msg.answer("Hoặc dùng menu nhanh phía dưới.", reply_markup=USER_REPLY_KB)


async def configure_bot_commands():
    default_cmds = [
        BotCommand(command="start", description="Mở menu"),
        BotCommand(command="menu", description="Hiển thị lại menu"),
    ]
    admin_cmds = default_cmds + [
        BotCommand(command="admin", description="Bảng điều khiển admin"),
    ]
    await bot.set_my_commands(default_cmds, scope=BotCommandScopeDefault())
    await bot.set_my_commands(admin_cmds, scope=BotCommandScopeChat(chat_id=ADMIN_ID))


def build_admin_stats_text() -> str:
    db = load_db()
    total_users = len(db["users"])
    don_cho = len([d for d in db["don"] if d["status"] == 0])
    balance_total = sum(user.get("balance", 0) for user in db["users"].values())
    return (
        "👑 *BẢNG ĐIỀU KHIỂN ADMIN*\n\n"
        f"👥 Người dùng: `{total_users}`\n"
        f"📦 Đơn chờ: `{don_cho}`\n"
        f"💰 Tổng số dư người dùng: `{balance_total}`"
    )


def build_kho_preview(limit: int = 5) -> str:
    kho_items = get_kho_available()[:limit]
    if not kho_items:
        return "(Kho đang trống)"

    lines = []
    for item in kho_items:
        lines.append(
            f"#{item['id']} • {item['so_diem']} điểm • {item['gia']}đ\n"
            f"├─ TK chưa liên kết: {item['ds_game']}\n"
            f"└─ TK chứa điểm: {item['ghichu']}"
        )
    return "\n\n".join(lines)


async def send_admin_dashboard(target: types.CallbackQuery | types.Message):
    text = build_admin_stats_text()
    await send_with_context(target, text, parse_mode="Markdown", reply_markup=ADMIN_MENU_KB)


@dp.message(Command("start"))
async def start_cmd(msg: types.Message):
    await send_user_welcome(msg)


@dp.message(Command("menu"))
async def menu_cmd(msg: types.Message):
    await send_user_welcome(msg)


@dp.message(Command("admin"))
async def admin_cmd(msg: types.Message):
    if msg.from_user.id != ADMIN_ID:
        return await msg.answer("⛔ Bạn không có quyền truy cập tính năng này.")

    await send_admin_dashboard(msg)


def clear_admin_pending(user_id: int):
    admin_pending.pop(user_id, None)


async def send_admin_pending(target: types.CallbackQuery | types.Message):
    db = load_db()
    pending = sorted(
        (d for d in db["don"] if d["status"] == 0),
        key=lambda d: d["time"],
        reverse=True,
    )
    if not pending:
        text = "📦 *ĐƠN CHỜ*\n\n✅ Không có đơn nào đang chờ xử lý."
    else:
        lines = []
        for d in pending[:5]:
            lines.append(
                f"#{d['id']} • User `{d['user_id']}` • {d['so_diem']} điểm • {d['so_tien']}đ • {d['game']}"
            )
        text = "📦 *ĐƠN CHỜ*\n\n" + "\n".join(lines)

    await send_with_context(target, text, parse_mode="Markdown", reply_markup=ADMIN_MENU_KB)


async def prompt_admin_add_kho(target: types.CallbackQuery | types.Message):
    admin_pending[target.from_user.id] = "add_kho"
    text = (
        "➕ *THÊM ĐIỂM VÀO KHO*\n\n"
        "Nhập theo định dạng: `diem|tk chưa liên kết|tk chứa điểm`\n"
        "Ví dụ: `100|TKChuaLK|TKChuaDiem`.\n"
        "Bot sẽ tự tính giá (100 điểm = 50.000đ)."
    )
    await send_with_context(target, text, parse_mode="Markdown", reply_markup=ADMIN_MENU_KB)


async def prompt_admin_remove_kho(target: types.CallbackQuery | types.Message):
    available_preview = build_kho_preview()
    admin_pending[target.from_user.id] = "remove_kho"
    text = (
        "🗑 *XÓA ĐIỂM KHỎI KHO*\n\n"
        "Gửi ID kho muốn xóa (xem danh sách dưới).\n\n"
        f"{available_preview}"
    )
    await send_with_context(target, text, parse_mode="Markdown", reply_markup=ADMIN_MENU_KB)


@dp.callback_query(
    F.data.in_(
        {
            "admin_stats",
            "admin_pending",
            "admin_back_user",
            "admin_add_kho",
            "admin_remove_kho",
        }
    )
)
async def admin_menu_callback(cb: types.CallbackQuery):
    if cb.from_user.id != ADMIN_ID:
        return await cb.answer("Không có quyền.", show_alert=True)

    if cb.data in {"admin_stats", "admin_pending", "admin_back_user"}:
        clear_admin_pending(cb.from_user.id)

    if cb.data == "admin_stats":
        await send_admin_dashboard(cb)
    elif cb.data == "admin_pending":
        await send_admin_pending(cb)
    elif cb.data == "admin_add_kho":
        await prompt_admin_add_kho(cb)
    elif cb.data == "admin_remove_kho":
        await prompt_admin_remove_kho(cb)
    else:
        text = build_user_menu_text(cb.from_user)
        await send_with_context(cb, text, parse_mode="Markdown", reply_markup=USER_INLINE_KB)


async def show_muadiem(target: types.CallbackQuery | types.Message):
    kho = get_kho_available()
    if not kho:
        return await send_with_context(target, "⚠️ Chưa có tài khoản nào trong kho!")

    text = "📦 *DANH SÁCH TÀI KHOẢN:*\n\n"
    for i, k in enumerate(kho, start=1):
        text += f"{i}. `{k['so_diem']}` điểm – *{k['ds_game']}* – `{k['gia']}đ`\n"

    user_id = target.from_user.id
    pending_step[user_id] = ("chon_so", kho)
    await send_with_context(target, text + "\nGửi số thứ tự muốn mua:", parse_mode="Markdown")


@dp.callback_query(F.data == "muadiem")
async def muadiem(cb: types.CallbackQuery):
    await show_muadiem(cb)


@dp.message(F.text == "🛒 Mua Điểm")
async def muadiem_text(msg: types.Message):
    await show_muadiem(msg)


@dp.message(lambda msg: msg.from_user.id in pending_step)
async def handle_buy_step(msg: types.Message):
    uid = msg.from_user.id

    step, data = pending_step.get(uid)

    if step == "chon_so":
        if not msg.text.isdigit():
            return await msg.answer("Gửi số thứ tự hợp lệ!")

        idx = int(msg.text)
        kho = data

        if idx < 1 or idx > len(kho):
            return await msg.answer("Số không hợp lệ!")

        selected = kho[idx - 1]
        update_user(uid, "pending_kho", selected["id"])

        pending_step[uid] = ("cho_tkgame", selected)

        return await msg.answer(
            f"Bạn muốn rút game nào?\n➡️ {selected['ds_game']}\n\n" "Gửi định dạng: `ten|4so`",
            parse_mode="Markdown",
        )

    elif step == "cho_tkgame":
        if "|" not in msg.text:
            return await msg.answer("Sai định dạng! Ví dụ: user001|2723")

        tk_game, so4 = msg.text.split("|", 1)

        db = load_db()
        kho_id = db["users"][str(uid)]["pending_kho"]
        item = next(k for k in db["kho"] if k["id"] == kho_id)

        don_id = add_don(
            user_id=uid,
            kho_id=kho_id,
            so_diem=item["so_diem"],
            so_tien=item["gia"],
            game=item["ds_game"],
            tk_game=tk_game,
            so4=so4,
        )

        mark_kho_sold(kho_id)

        btn = InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(text="✔ Thành Công", callback_data=f"ok_{don_id}"),
                    InlineKeyboardButton(text="⏳ Đang xử lý", callback_data=f"wait_{don_id}"),
                    InlineKeyboardButton(text="❌ Thất bại", callback_data=f"fail_{don_id}"),
                ]
            ]
        )

        msg_admin = f"""
📌 *USER ĐÃ MUA ĐIỂM*

🆔 User: `{uid}`
🎯 Số điểm: `{item['so_diem']}`
💵 Giá: `{item['gia']}đ`
🎮 Game: *{item['ds_game']}*
👤 TK Game: `{tk_game}`
📞 4 số: `{so4}`

📦 Nick OKVIP: `{item['ghichu']}`
⏳ Đơn ID: `{don_id}`
"""
        await bot.send_message(ADMIN_ID, msg_admin, parse_mode="Markdown", reply_markup=btn)

        await msg.answer("Đã tạo đơn! Admin sẽ xử lý sớm nhất.")
        del pending_step[uid]


@dp.message(lambda msg: msg.from_user.id == ADMIN_ID and msg.from_user.id in admin_pending)
async def handle_admin_pending_message(msg: types.Message):
    action = admin_pending.get(msg.from_user.id)

    if action == "add_kho":
        parts = [p.strip() for p in msg.text.split("|")]
        if len(parts) != 3:
            return await msg.answer("Sai định dạng! Ví dụ: 100|TKChuaLK|TKChuaDiem")

        try:
            so_diem = int(parts[0])
        except ValueError:
            return await msg.answer("Số điểm phải là số nguyên.")

        if so_diem <= 0:
            return await msg.answer("Số điểm phải lớn hơn 0.")

        entry = create_kho_entry(so_diem, parts[1], parts[2])
        db = load_db()
        db["kho"].append(entry)
        save_db(db)

        clear_admin_pending(msg.from_user.id)
        text = (
            "✅ Đã thêm kho mới!\n\n"
            f"ID: {entry['id']}\n"
            f"Điểm: {entry['so_diem']}\n"
            f"Giá: {entry['gia']}đ\n"
            f"TK chưa liên kết: {entry['ds_game']}\n"
            f"TK chứa điểm: {entry['ghichu']}"
        )
        await msg.answer(text)
    elif action == "remove_kho":
        if not msg.text.isdigit():
            return await msg.answer("Gửi ID hợp lệ (chỉ gồm số).")

        kho_id = int(msg.text)
        db = load_db()
        before_len = len(db["kho"])
        db["kho"] = [item for item in db["kho"] if item["id"] != kho_id]

        if len(db["kho"]) == before_len:
            return await msg.answer("Không tìm thấy ID này trong kho.")

        save_db(db)
        clear_admin_pending(msg.from_user.id)
        await msg.answer(f"🗑 Đã xóa kho ID {kho_id}.")


async def show_naptien(target: types.CallbackQuery | types.Message):
    uid = target.from_user.id
    text = f"""
💳 *NẠP TIỀN OKVIP BOT*

STK: `{BANK_STK}`
Ngân hàng: `{BANK_BANK}`
Chủ TK: *{BANK_NAME}*

Nội dung chuyển khoản:
➡️ `NAP{uid}`

Sau khi nạp bot sẽ cộng tự động qua SEPAY webhook.
"""
    await send_with_context(target, text, parse_mode="Markdown")


@dp.callback_query(F.data == "naptien")
async def naptien(cb: types.CallbackQuery):
    await show_naptien(cb)


@dp.message(F.text == "💳 Nạp Tiền")
async def naptien_text(msg: types.Message):
    await show_naptien(msg)


async def show_lichsu(target: types.CallbackQuery | types.Message):
    db = load_db()
    uid = str(target.from_user.id)
    don = [d for d in db["don"] if str(d["user_id"]) == uid]
    if not don:
        return await send_with_context(target, "Bạn chưa có lịch sử giao dịch nào.")

    don.sort(key=lambda d: d["time"], reverse=True)
    lines = [
        f"#{d['id']} - {d['game']} - {d['so_diem']} điểm - {d['so_tien']}đ - trạng thái {d['status']}"
        for d in don[:5]
    ]
    await send_with_context(target, "\n".join(lines))


@dp.callback_query(F.data == "lichsu")
async def lichsu(cb: types.CallbackQuery):
    await show_lichsu(cb)


@dp.message(F.text == "📚 Lịch Sử")
async def lichsu_text(msg: types.Message):
    await show_lichsu(msg)


async def show_hoso(target: types.CallbackQuery | types.Message):
    user = get_user(target.from_user.id)
    text = (
        "👤 *HỒ SƠ CỦA BẠN*\n\n"
        f"Số dư: `{user['balance']}`\n"
        f"Tổng nạp: `{user['total_nap']}`\n"
        f"Tổng dùng: `{user['total_dung']}`"
    )
    await send_with_context(target, text, parse_mode="Markdown")


@dp.callback_query(F.data == "hoso")
async def hoso(cb: types.CallbackQuery):
    await show_hoso(cb)


@dp.message(F.text == "👤 Hồ Sơ")
async def hoso_text(msg: types.Message):
    await show_hoso(msg)


async def show_hotro(target: types.CallbackQuery | types.Message):
    await send_with_context(target, "Vui lòng liên hệ @admin để được hỗ trợ.")


@dp.callback_query(F.data == "hotro")
async def hotro(cb: types.CallbackQuery):
    await show_hotro(cb)


@dp.message(F.text == "📨 Hỗ Trợ")
async def hotro_text(msg: types.Message):
    await show_hotro(msg)


@dp.callback_query(F.data.startswith(("ok_", "wait_", "fail_")))
async def admin_duyet(cb: types.CallbackQuery):
    if cb.from_user.id != ADMIN_ID:
        return await cb.answer("Không có quyền.", show_alert=True)

    data = cb.data
    action, don_id = data.split("_")
    don_id = int(don_id)

    db = load_db()
    for d in db["don"]:
        if d["id"] == don_id:
            if action == "ok":
                d["status"] = 2
                status_text = "✔ THÀNH CÔNG"
            elif action == "wait":
                d["status"] = 1
                status_text = "⏳ ĐANG XỬ LÝ"
            else:
                d["status"] = 3
                status_text = "❌ THẤT BẠI"

            save_db(db)
            await cb.message.edit_text(
                cb.message.text + f"\n\nCập nhật: *{status_text}*", parse_mode="Markdown"
            )
            break


async def sepay_handler(request):
    data = await request.json()
    desc = data.get("description", "")
    amount = int(data.get("amount", 0))

    if not desc.startswith("NAP"):
        return web.Response(text="IGNORED")

    uid = desc.replace("NAP", "")
    db = load_db()

    if uid not in db["users"]:
        return web.Response(text="NO USER")

    db["users"][uid]["balance"] += amount
    db["users"][uid]["total_nap"] += amount
    db["nap"].append({"user": uid, "amount": amount, "time": time.time()})

    save_db(db)

    await bot.send_message(uid, f"💸 Bạn đã nạp *{amount}đ* thành công!", parse_mode="Markdown")
    await bot.send_message(ADMIN_ID, f"⚡ User `{uid}` vừa nạp `{amount}đ`", parse_mode="Markdown")

    asyncio.create_task(forward_webhook(
        {
            "user": uid,
            "amount": amount,
            "description": desc,
            "raw": data,
        }
    ))

    return web.Response(text="OK")


async def run_webhook():
    app = web.Application()
    app.router.add_post(SEPAY_PATH, sepay_handler)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", WEBHOOK_PORT)
    await site.start()
    print(f"Webhook chạy tại: http://0.0.0.0:{WEBHOOK_PORT}{SEPAY_PATH}")


async def forward_webhook(payload: dict):
    if not FORWARD_WEBHOOK_URL:
        return

    try:
        async with ClientSession() as session:
            async with session.post(FORWARD_WEBHOOK_URL, json=payload, timeout=10) as resp:
                if resp.status >= 400:
                    text = await resp.text()
                    print(
                        f"Forward webhook thất bại ({resp.status}): {text[:200]}"
                    )
    except Exception as exc:  # noqa: BLE001 - chỉ log
        print(f"Forward webhook lỗi: {exc}")


async def main():
    await configure_bot_commands()
    asyncio.create_task(run_webhook())
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())

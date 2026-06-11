"""
Riverside Home Guide
An AI-powered tool for first-time home buyers in Murrieta, Temecula,
and Riverside County, California.

Run it with:  python app.py
Then open:    http://localhost:5000

Required environment variables (all set in .env):
  GOOGLE_API_KEY        -- from aistudio.google.com (free)
  STRIPE_SECRET_KEY     -- from dashboard.stripe.com
  STRIPE_WEBHOOK_SECRET -- from dashboard.stripe.com -> Webhooks
  FLASK_SECRET_KEY      -- long random string (already generated)
  DEBUG                 -- true for local dev, false for production
"""

import os
import sqlite3
from datetime import datetime, timedelta, timezone

from dotenv import load_dotenv
load_dotenv()

from google import genai
from google.genai import types as genai_types
import stripe
from flask import (Flask, jsonify, redirect, render_template,
                   request, session, url_for)

# ---------- Config ----------

_debug = os.environ.get('DEBUG', 'false').lower() == 'true'
BASE_URL     = os.environ.get('BASE_URL', '').rstrip('/')
DATABASE_URL = os.environ.get('DATABASE_URL', '')
_PG = bool(DATABASE_URL)   # True when running on Render with PostgreSQL
_PH = '%s' if _PG else '?' # SQL parameter placeholder

app = Flask(__name__)
app.secret_key = os.environ.get('FLASK_SECRET_KEY', 'dev-secret-change-before-going-live')
app.config['PERMANENT_SESSION_LIFETIME'] = timedelta(days=365)
app.config['SESSION_COOKIE_HTTPONLY'] = True
app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'
app.config['SESSION_COOKIE_SECURE'] = not _debug


@app.before_request
def make_session_permanent():
    session.permanent = True


# ---------- Gemini setup ----------

GEMINI_MODEL  = 'gemini-flash-latest'
AI_PRICE_CENTS = 4000   # $40.00
DAILY_LIMIT    = 50     # max AI questions per user per day
MAX_HISTORY    = 20     # max messages sent per request
MAX_MSG_LEN    = 2000   # max characters per message

SYSTEM_PROMPT = (
    "You are a friendly first-time home buying guide specialized in Murrieta, "
    "Temecula, and Riverside County California. You explain everything in plain "
    "simple language like you are talking to someone who has never bought a home "
    "before. You know FHA loans, down payment assistance programs, escrow, DTI, "
    "PMI, and closing costs. Never use jargon without explaining it first."
)

def _build_gemini():
    api_key = os.environ.get('GOOGLE_API_KEY', '')
    if not api_key or api_key == 'YOUR_GOOGLE_API_KEY_HERE':
        return None
    return genai.Client(api_key=api_key)

_gemini = _build_gemini()

# ---------- Stripe setup ----------

stripe.api_key = os.environ.get('STRIPE_SECRET_KEY', '')

# ---------- Database ----------

DB_PATH = os.path.join(os.path.dirname(__file__), 'payments.db')


def _db():
    """Return a db connection that works with both SQLite (local) and PostgreSQL (Render)."""
    if _PG:
        import psycopg2
        url = DATABASE_URL.replace('postgres://', 'postgresql://', 1)
        raw = psycopg2.connect(url)
        raw.autocommit = False
        def _exec(sql, params=None):
            cur = raw.cursor()
            cur.execute(sql, params or [])
            return cur
        raw.execute = _exec
        return raw
    return sqlite3.connect(DB_PATH)


def init_db():
    conn = _db()
    try:
        conn.execute('''
            CREATE TABLE IF NOT EXISTS paid_emails (
                email              TEXT PRIMARY KEY,
                stripe_session_id  TEXT,
                paid_at            TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        conn.execute('''
            CREATE TABLE IF NOT EXISTS daily_usage (
                email  TEXT,
                date   TEXT,
                count  INTEGER DEFAULT 0,
                PRIMARY KEY (email, date)
            )
        ''')
        conn.commit()
    finally:
        conn.close()


def mark_email_paid(email: str, stripe_session_id: str):
    conn = _db()
    try:
        if _PG:
            conn.execute(
                '''INSERT INTO paid_emails (email, stripe_session_id) VALUES (%s, %s)
                   ON CONFLICT (email) DO UPDATE SET stripe_session_id = EXCLUDED.stripe_session_id''',
                [email.lower().strip(), stripe_session_id],
            )
        else:
            conn.execute(
                'INSERT OR REPLACE INTO paid_emails (email, stripe_session_id) VALUES (?, ?)',
                [email.lower().strip(), stripe_session_id],
            )
        conn.commit()
    finally:
        conn.close()


def is_email_paid(email: str) -> bool:
    conn = _db()
    try:
        row = conn.execute(
            f'SELECT 1 FROM paid_emails WHERE email = {_PH}',
            [email.lower().strip()],
        ).fetchone()
        return row is not None
    finally:
        conn.close()


def get_daily_usage(email: str) -> int:
    today = datetime.now(timezone.utc).strftime('%Y-%m-%d')
    conn = _db()
    try:
        row = conn.execute(
            f'SELECT count FROM daily_usage WHERE email = {_PH} AND date = {_PH}',
            [email.lower().strip(), today],
        ).fetchone()
        return row[0] if row else 0
    finally:
        conn.close()


def increment_daily_usage(email: str):
    today = datetime.now(timezone.utc).strftime('%Y-%m-%d')
    conn = _db()
    try:
        if _PG:
            conn.execute(
                '''INSERT INTO daily_usage (email, date, count) VALUES (%s, %s, 1)
                   ON CONFLICT (email, date) DO UPDATE SET count = daily_usage.count + 1''',
                [email.lower().strip(), today],
            )
        else:
            conn.execute(
                '''INSERT INTO daily_usage (email, date, count) VALUES (?, ?, 1)
                   ON CONFLICT(email, date) DO UPDATE SET count = count + 1''',
                [email.lower().strip(), today],
            )
        conn.commit()
    finally:
        conn.close()


init_db()

# ---------- Pages ----------

@app.route('/')
def home():
    return render_template('index.html', active='home')


@app.route('/ask')
def ask():
    if not session.get('paid'):
        return redirect(url_for('unlock'))
    return render_template('chat.html', active='ask')


@app.route('/calculator')
def calculator():
    return render_template('calculator.html', active='calculator')


@app.route('/property-check')
def property_check():
    return render_template('property_check.html', active='property_check')


@app.route('/closing-roadmap')
def closing_roadmap():
    return render_template('closing_roadmap.html', active='closing_roadmap')


@app.route('/checklist')
def checklist():
    return render_template('checklist.html', active='checklist')


@app.route('/glossary')
def glossary():
    return render_template('glossary.html', active='glossary')


@app.route('/calhfa')
def calhfa():
    return render_template('calhfa.html', active='calhfa')


@app.route('/profile')
def profile():
    if not session.get('paid'):
        return redirect(url_for('unlock'))
    email = session.get('user_email', '')
    usage = get_daily_usage(email) if email else 0
    return render_template('profile.html', active='profile', email=email, usage=usage,
                           daily_limit=DAILY_LIMIT)


@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('home'))


# ---------- Payment routes ----------

@app.route('/unlock')
def unlock():
    if session.get('paid'):
        return redirect(url_for('ask'))
    return render_template('unlock.html', active='ask', error=None)


@app.route('/checkout', methods=['POST'])
def checkout():
    email = request.form.get('email', '').strip().lower()
    if not email:
        return render_template('unlock.html', active='ask',
                               error='Please enter your email address.')

    if is_email_paid(email):
        session['paid'] = True
        session['user_email'] = email
        return redirect(url_for('ask'))

    if not stripe.api_key:
        return render_template('unlock.html', active='ask',
                               error='Payments are not configured yet. '
                                     'Set STRIPE_SECRET_KEY in .env and restart.')

    _base = BASE_URL or request.host_url.rstrip('/')
    try:
        checkout_session = stripe.checkout.Session.create(
            payment_method_types=['card'],
            line_items=[{
                'price_data': {
                    'currency': 'usd',
                    'unit_amount': AI_PRICE_CENTS,
                    'product_data': {
                        'name': 'Riverside Home Guide -- AI Access',
                        'description': 'Lifetime access to the AI home buying assistant',
                    },
                },
                'quantity': 1,
            }],
            mode='payment',
            customer_email=email,
            success_url=_base + '/success?session_id={CHECKOUT_SESSION_ID}',
            cancel_url=_base + '/unlock',
        )
    except stripe.error.StripeError as e:
        return render_template('unlock.html', active='ask',
                               error=f'Payment setup failed: {e.user_message}')

    session['pending_email'] = email
    return redirect(checkout_session.url, code=303)


@app.route('/success')
def payment_success():
    stripe_session_id = request.args.get('session_id', '')
    if not stripe_session_id or not stripe.api_key:
        return redirect(url_for('unlock'))

    try:
        checkout_session = stripe.checkout.Session.retrieve(stripe_session_id)
        if checkout_session.payment_status == 'paid':
            email = (
                checkout_session.customer_email or session.get('pending_email', '')
            ).lower().strip()
            if email:
                mark_email_paid(email, stripe_session_id)
                session['paid'] = True
                session['user_email'] = email
                session.pop('pending_email', None)
            return render_template('payment_success.html', active='ask')
    except stripe.error.StripeError:
        pass

    return redirect(url_for('unlock'))


@app.route('/webhook', methods=['POST'])
def stripe_webhook():
    payload       = request.data
    sig_header    = request.headers.get('Stripe-Signature', '')
    webhook_secret = os.environ.get('STRIPE_WEBHOOK_SECRET', '')

    if not webhook_secret or webhook_secret == 'whsec_YOUR_WEBHOOK_SECRET_HERE':
        return jsonify({'error': 'Webhook secret not configured'}), 400

    try:
        event = stripe.Webhook.construct_event(payload, sig_header, webhook_secret)
    except (ValueError, stripe.error.SignatureVerificationError):
        return jsonify({'error': 'Invalid signature'}), 400

    if event['type'] == 'checkout.session.completed':
        obj = event['data']['object']
        if obj.get('payment_status') == 'paid':
            email = (obj.get('customer_email') or '').lower().strip()
            if email:
                mark_email_paid(email, obj['id'])

    return jsonify({'received': True})


# ---------- AI chat API ----------

@app.route('/api/chat', methods=['POST'])
def api_chat():
    if not session.get('paid'):
        return jsonify({'error': 'Please unlock AI access first.'}), 403

    email = session.get('user_email', '')
    if email and get_daily_usage(email) >= DAILY_LIMIT:
        return jsonify({
            'error': (f'You have reached the {DAILY_LIMIT} question daily limit. '
                      'Come back tomorrow -- your access never expires.')
        }), 429

    # Re-build the model if the key was added after startup
    global _gemini
    if _gemini is None:
        _gemini = _build_gemini()

    if _gemini is None:
        return jsonify({
            'error': ('AI is not configured. Add GOOGLE_API_KEY to your .env file '
                      'and restart the app.')
        }), 401

    data    = request.get_json(silent=True) or {}
    history = data.get('messages', [])

    # Sanitize + cap history (cost control)
    clean = [
        {'role': m['role'], 'content': str(m['content'])[:MAX_MSG_LEN]}
        for m in history
        if isinstance(m, dict)
        and m.get('role') in ('user', 'assistant')
        and isinstance(m.get('content'), str)
        and m['content'].strip()
    ][-MAX_HISTORY:]

    if not clean or clean[-1]['role'] != 'user':
        return jsonify({'error': 'Please type a question first.'}), 400

    # Convert to Gemini format (uses "model" instead of "assistant")
    gemini_messages = [
        genai_types.Content(
            role='model' if m['role'] == 'assistant' else 'user',
            parts=[genai_types.Part(text=m['content'])],
        )
        for m in clean
    ]

    try:
        response = _gemini.models.generate_content(
            model=GEMINI_MODEL,
            contents=gemini_messages,
            config=genai_types.GenerateContentConfig(
                system_instruction=SYSTEM_PROMPT,
                max_output_tokens=2048,
            ),
        )
        reply = response.text
    except Exception as e:
        err = str(e).lower()
        if '429' in err or 'resource_exhausted' in err or 'quota exceeded' in err:
            return jsonify({'error': 'Too many requests. Wait a minute and try again.'}), 429
        if '401' in err or 'unauthenticated' in err or 'api key not valid' in err:
            return jsonify({'error': 'Google API key is invalid. Check GOOGLE_API_KEY in .env'}), 401
        return jsonify({'error': 'The AI service had a problem. Please try again.'}), 502

    if email:
        increment_daily_usage(email)
    return jsonify({'reply': reply})


if __name__ == '__main__':
    missing = []
    if not os.environ.get('GOOGLE_API_KEY') or \
            os.environ.get('GOOGLE_API_KEY') == 'YOUR_GOOGLE_API_KEY_HERE':
        missing.append('GOOGLE_API_KEY  -- free at aistudio.google.com')
    if not os.environ.get('STRIPE_SECRET_KEY'):
        missing.append('STRIPE_SECRET_KEY  -- dashboard.stripe.com')
    if not os.environ.get('STRIPE_WEBHOOK_SECRET') or \
            os.environ.get('STRIPE_WEBHOOK_SECRET') == 'whsec_YOUR_WEBHOOK_SECRET_HERE':
        print('TIP: Set STRIPE_WEBHOOK_SECRET before going live with real payments.')
    if not os.environ.get('FLASK_SECRET_KEY'):
        print('WARNING: FLASK_SECRET_KEY not set -- using insecure default.')

    if missing:
        print('=' * 60)
        print('Add these to your .env file:')
        for m in missing:
            print(f'  {m}')
        print('=' * 60)

    if _debug:
        app.run(debug=True)
    else:
        from waitress import serve
        print('Starting production server on http://0.0.0.0:5000')
        serve(app, host='0.0.0.0', port=5000)

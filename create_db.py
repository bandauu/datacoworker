"""
Create SaaS Analytics Database for Data Coworker
"""
import os
import sqlite3
import random
from datetime import datetime, timedelta

def create_saas_database():
    os.makedirs('database', exist_ok=True)
    conn = sqlite3.connect('database/saas_analytics.db')
    cursor = conn.cursor()
    
    # Drop existing tables
    for table in ['users', 'subscriptions', 'usage_metrics', 'revenue', 'support_tickets', 'feature_adoption']:
        cursor.execute(f'DROP TABLE IF EXISTS {table}')
    
    # Create tables
    cursor.execute('''CREATE TABLE users (
        user_id INTEGER PRIMARY KEY, company_name TEXT, email TEXT, 
        industry TEXT, signup_date DATE, status TEXT)''')
    
    cursor.execute('''CREATE TABLE subscriptions (
        subscription_id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER,
        plan_name TEXT, mrr REAL, start_date DATE, end_date DATE, status TEXT)''')
    
    cursor.execute('''CREATE TABLE usage_metrics (
        metric_id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER,
        feature_name TEXT, usage_count INTEGER, date DATE)''')
    
    cursor.execute('''CREATE TABLE revenue (
        transaction_id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER,
        amount REAL, transaction_type TEXT, date DATE)''')
    
    cursor.execute('''CREATE TABLE support_tickets (
        ticket_id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER,
        priority TEXT, status TEXT, created_date DATE, resolved_date DATE)''')
    
    cursor.execute('''CREATE TABLE feature_adoption (
        adoption_id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER,
        feature_name TEXT, first_used_date DATE, total_usage INTEGER)''')
    
    # Generate data
    industries = ['Technology', 'Finance', 'Healthcare', 'Retail', 'Education']
    features = ['Dashboard', 'API Access', 'Reports', 'Integrations', 'Analytics', 'Automation']
    
    # Users (50)
    users_data = []
    for i in range(1, 51):
        signup_days_ago = random.randint(30, 365)
        signup_date = (datetime.now() - timedelta(days=signup_days_ago)).strftime('%Y-%m-%d')
        status = 'active' if random.random() > 0.25 else 'churned'
        users_data.append((i, f"Company_{i}", f"admin@company{i}.com", 
                          random.choice(industries), signup_date, status))
    cursor.executemany('INSERT INTO users VALUES (?,?,?,?,?,?)', users_data)
    
    # Subscriptions
    plan_prices = {'Free': 0, 'Starter': 49, 'Professional': 199, 'Enterprise': 999}
    for user_id in range(1, 51):
        plan = random.choice(['Starter', 'Starter', 'Professional', 'Enterprise'])
        cursor.execute('SELECT signup_date, status FROM users WHERE user_id=?', (user_id,))
        signup_date, user_status = cursor.fetchone()
        cursor.execute('''INSERT INTO subscriptions (user_id, plan_name, mrr, start_date, status) 
                         VALUES (?,?,?,?,?)''', (user_id, plan, plan_prices[plan], signup_date, user_status))
    
    # Usage metrics (last 30 days) - LOW USAGE for some users to trigger alerts
    for user_id in range(1, 51):
        cursor.execute('SELECT status FROM users WHERE user_id=?', (user_id,))
        status = cursor.fetchone()[0]
        usage_level = random.randint(1, 3) if status == 'active' else 0  # Some low usage
        
        for days_ago in range(30):
            date = (datetime.now() - timedelta(days=days_ago)).strftime('%Y-%m-%d')
            if usage_level > 0:
                for _ in range(usage_level):
                    cursor.execute('''INSERT INTO usage_metrics (user_id, feature_name, usage_count, date)
                                     VALUES (?,?,?,?)''', (user_id, random.choice(features), 
                                     random.randint(1, 20), date))
    
    # Revenue (MRR drops - ALERT TRIGGER)
    today_revenue = 0
    for month in range(3):
        date = (datetime.now() - timedelta(days=month*30)).strftime('%Y-%m-%d')
        month_revenue = 0
        cursor.execute('SELECT user_id, mrr FROM subscriptions WHERE status="active"')
        for user_id, mrr in cursor.fetchall():
            # Simulate revenue drop in current month
            if month == 0:
                amount = mrr * 0.75  # 25% drop THIS MONTH (triggers alert!)
            else:
                amount = mrr
            cursor.execute('INSERT INTO revenue (user_id, amount, transaction_type, date) VALUES (?,?,?,?)',
                          (user_id, amount, 'subscription', date))
            month_revenue += amount
            if month == 0:
                today_revenue = month_revenue
    
    # Support tickets (HIGH PRIORITY ONES - ALERT TRIGGER)
    for _ in range(15):  # Create some urgent tickets
        user_id = random.randint(1, 50)
        cursor.execute('''INSERT INTO support_tickets (user_id, priority, status, created_date)
                         VALUES (?,?,?,?)''', (user_id, 'urgent', 'open', datetime.now().strftime('%Y-%m-%d')))
    
    # Feature adoption
    for user_id in range(1, 51):
        for feature in random.sample(features, random.randint(2, 5)):
            cursor.execute('''INSERT INTO feature_adoption (user_id, feature_name, first_used_date, total_usage)
                             VALUES (?,?,?,?)''', (user_id, feature, 
                             (datetime.now() - timedelta(days=random.randint(10, 60))).strftime('%Y-%m-%d'),
                             random.randint(10, 200)))
    
    conn.commit()
    
    # Summary
    print("✅ SaaS Database Created: database/saas_analytics.db\n")
    print(f"📊 Users: {cursor.execute('SELECT COUNT(*) FROM users').fetchone()[0]}")
    mrr = cursor.execute("SELECT SUM(mrr) FROM subscriptions WHERE status='active'").fetchone()[0]
    print(f"💰 Total MRR: ${mrr:.2f}")
    urgent = cursor.execute("SELECT COUNT(*) FROM support_tickets WHERE priority='urgent' AND status='open'").fetchone()[0]
    print(f"⚠️  Urgent Tickets: {urgent}")
    print(f"📉 Revenue Drop: ~25% (alert triggered!)\n")
    
    conn.close()

if __name__ == '__main__':
    create_saas_database()

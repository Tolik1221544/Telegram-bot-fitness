import matplotlib.pyplot as plt
import matplotlib.dates as mdates
from datetime import datetime, timedelta
import seaborn as sns
import tempfile
from typing import List, Tuple
from sqlalchemy import select, func
from bot.database import LwCoinTransaction, Payment

plt.style.use('seaborn-v0_8-darkgrid')
sns.set_palette("husl")


async def generate_spending_chart_from_db(db_session, days: int = 30) -> str:
    """
    Generate coin spending chart from database

    Args:
        db_session: Database session
        days: Number of days to show (default: 30)

    Returns:
        Path to generated chart file
    """
    start_date = datetime.utcnow() - timedelta(days=days)

    result = await db_session.execute(
        select(
            CoinSpending.date,
            func.sum(CoinSpending.amount).label('total')
        )
        .where(CoinSpending.timestamp >= start_date)
        .group_by(CoinSpending.date)
        .order_by(CoinSpending.date)
    )

    data = result.all()

    if not data:
        raise ValueError(f"No spending data for last {days} days")

    return await generate_spending_chart(data)


async def generate_spending_chart(data: List[Tuple]) -> str:
    """Generate coin spending chart from data"""
    fig, ax = plt.subplots(figsize=(12, 6))

    dates = [datetime.strptime(row[0], '%Y-%m-%d') for row in data]
    amounts = [row[1] for row in data]

    ax.plot(dates, amounts, marker='o', linewidth=2, markersize=8)
    ax.fill_between(dates, amounts, alpha=0.3)

    ax.set_xlabel('Дата', fontsize=12)
    ax.set_ylabel('Потрачено монет', fontsize=12)
    ax.set_title('График трат монет за последние 30 дней', fontsize=14, fontweight='bold')

    # Format x-axis
    ax.xaxis.set_major_formatter(mdates.DateFormatter('%d.%m'))
    ax.xaxis.set_major_locator(mdates.DayLocator(interval=5))
    plt.xticks(rotation=45)

    # Add grid
    ax.grid(True, alpha=0.3)

    # Add average line
    avg = sum(amounts) / len(amounts)
    ax.axhline(y=avg, color='r', linestyle='--', alpha=0.7, label=f'Среднее: {avg:.1f}')

    ax.legend()

    plt.tight_layout()

    # Save to temporary file
    temp_file = tempfile.NamedTemporaryFile(suffix='.png', delete=False)
    plt.savefig(temp_file.name, dpi=100, bbox_inches='tight')
    plt.close()

    return temp_file.name


async def generate_revenue_chart_from_db(db_session, days: int = 30) -> str:
    """
    Generate revenue chart from database

    Args:
        db_session: Database session
        days: Number of days to show (default: 30)

    Returns:
        Path to generated chart file
    """
    start_date = datetime.utcnow() - timedelta(days=days)

    result = await db_session.execute(
        select(
            func.date(Payment.completed_at).label('date'),
            func.sum(Payment.amount).label('total')
        )
        .where(Payment.status == 'completed')
        .where(Payment.completed_at >= start_date)
        .group_by(func.date(Payment.completed_at))
        .order_by(func.date(Payment.completed_at))
    )

    data = result.all()

    if not data:
        raise ValueError(f"No revenue data for last {days} days")

    return await generate_revenue_chart(data)


async def generate_revenue_chart(data: List[Tuple]) -> str:
    """Generate revenue chart from data"""
    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(12, 10))

    dates = [row[0] for row in data]
    amounts = [row[1] for row in data]

    # Daily revenue
    ax1.bar(range(len(dates)), amounts, color='green', alpha=0.7)
    ax1.set_xlabel('Дата', fontsize=12)
    ax1.set_ylabel('Доход (₽)', fontsize=12)
    ax1.set_title('Ежедневный доход', fontsize=14, fontweight='bold')
    ax1.set_xticks(range(len(dates)))
    ax1.set_xticklabels([d.strftime('%d.%m') if isinstance(d, datetime) else d for d in dates], rotation=45)

    # Add value labels on bars
    for i, v in enumerate(amounts):
        ax1.text(i, v + max(amounts) * 0.01, f'{v:.0f}', ha='center', va='bottom')

    # Cumulative revenue
    cumulative = []
    total = 0
    for amount in amounts:
        total += amount
        cumulative.append(total)

    ax2.plot(range(len(dates)), cumulative, marker='o', linewidth=2, markersize=8, color='blue')
    ax2.fill_between(range(len(dates)), cumulative, alpha=0.3)
    ax2.set_xlabel('Дата', fontsize=12)
    ax2.set_ylabel('Накопленный доход (₽)', fontsize=12)
    ax2.set_title('Накопленный доход', fontsize=14, fontweight='bold')
    ax2.set_xticks(range(len(dates)))
    ax2.set_xticklabels([d.strftime('%d.%m') if isinstance(d, datetime) else d for d in dates], rotation=45)

    # Add grid
    ax1.grid(True, alpha=0.3)
    ax2.grid(True, alpha=0.3)

    plt.tight_layout()

    # Save to temporary file
    temp_file = tempfile.NamedTemporaryFile(suffix='.png', delete=False)
    plt.savefig(temp_file.name, dpi=100, bbox_inches='tight')
    plt.close()

    return temp_file.name


async def generate_user_stats_chart(user_data: dict) -> str:
    """Generate user statistics chart"""
    fig, ((ax1, ax2), (ax3, ax4)) = plt.subplots(2, 2, figsize=(12, 10))

    # Pie chart for feature usage
    features = list(user_data['feature_usage'].keys())
    usage = list(user_data['feature_usage'].values())

    ax1.pie(usage, labels=features, autopct='%1.1f%%', startangle=90)
    ax1.set_title('Использование функций')

    # Bar chart for daily activity
    days = list(user_data['daily_activity'].keys())
    activity = list(user_data['daily_activity'].values())

    ax2.bar(days, activity, color='skyblue')
    ax2.set_xlabel('День недели')
    ax2.set_ylabel('Активность')
    ax2.set_title('Активность по дням')

    # Line chart for coin balance history
    dates = list(user_data['balance_history'].keys())
    balance = list(user_data['balance_history'].values())

    ax3.plot(dates, balance, marker='o', color='gold')
    ax3.set_xlabel('Дата')
    ax3.set_ylabel('Баланс')
    ax3.set_title('История баланса')
    ax3.tick_params(axis='x', rotation=45)

    # Stats summary
    ax4.axis('off')
    stats_text = f"""
    Всего потрачено: {user_data['total_spent']} монет
    Всего заработано: {user_data['total_earned']} монет
    Дней активности: {user_data['active_days']}
    Рефералов: {user_data['referrals']}
    """
    ax4.text(0.5, 0.5, stats_text, ha='center', va='center', fontsize=12)
    ax4.set_title('Общая статистика')

    plt.tight_layout()

    # Save to temporary file
    temp_file = tempfile.NamedTemporaryFile(suffix='.png', delete=False)
    plt.savefig(temp_file.name, dpi=100, bbox_inches='tight')
    plt.close()

    return temp_file.name
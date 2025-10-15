import matplotlib.pyplot as plt
import matplotlib.dates as mdates
from datetime import datetime, timedelta
import seaborn as sns
import tempfile
from typing import List, Dict, Any

plt.style.use('seaborn-v0_8-darkgrid')
sns.set_palette("husl")


async def generate_spending_chart_from_server_data(daily_stats: List[Dict]) -> str:
    fig, ax = plt.subplots(figsize=(12, 6))

    dates = []
    amounts = []

    for stat in daily_stats:
        date_str = stat.get('Date', stat.get('date', ''))
        if date_str:
            try:
                date = datetime.strptime(date_str, '%Y-%m-%d')
                dates.append(date)
                amounts.append(stat.get('TotalSpent', stat.get('totalSpent', 0)))
            except:
                continue

    if not dates:
        raise ValueError("No valid data for chart")

    sorted_data = sorted(zip(dates, amounts), key=lambda x: x[0])
    dates, amounts = zip(*sorted_data)

    ax.plot(dates, amounts, marker='o', linewidth=2, markersize=8, color='#FF6B6B')
    ax.fill_between(dates, amounts, alpha=0.3, color='#FF6B6B')

    ax.set_xlabel('Дата', fontsize=12)
    ax.set_ylabel('Потрачено монет', fontsize=12)
    ax.set_title('График трат монет', fontsize=14, fontweight='bold')

    ax.xaxis.set_major_formatter(mdates.DateFormatter('%d.%m'))
    if len(dates) > 15:
        ax.xaxis.set_major_locator(mdates.DayLocator(interval=5))
    else:
        ax.xaxis.set_major_locator(mdates.DayLocator(interval=2))
    plt.xticks(rotation=45)

    ax.grid(True, alpha=0.3)

    if amounts:
        avg = sum(amounts) / len(amounts)
        ax.axhline(y=avg, color='r', linestyle='--', alpha=0.7,
                   label=f'Среднее: {avg:.1f} монет')
        ax.legend()

    # Добавляем значения на точках для лучшей читаемости
    for i, (date, amount) in enumerate(zip(dates, amounts)):
        if i % max(1, len(dates) // 10) == 0:  # Показываем каждое N-ое значение
            ax.annotate(f'{amount:.0f}',
                        xy=(date, amount),
                        xytext=(0, 5),
                        textcoords='offset points',
                        ha='center',
                        fontsize=8,
                        alpha=0.7)

    plt.tight_layout()

    # Сохраняем в временный файл
    temp_file = tempfile.NamedTemporaryFile(suffix='.png', delete=False)
    plt.savefig(temp_file.name, dpi=100, bbox_inches='tight')
    plt.close()

    return temp_file.name


async def generate_revenue_chart_from_server_data(daily_revenue: List[Dict],
                                                  coin_purchases: List[Dict] = None) -> str:
    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(12, 10))

    dates = []
    amounts = []

    for revenue in daily_revenue:
        date_str = revenue.get('Date', revenue.get('date', ''))
        if date_str:
            try:
                if isinstance(date_str, str):
                    date = datetime.strptime(date_str, '%Y-%m-%d')
                else:
                    date = date_str
                dates.append(date)
                amounts.append(float(revenue.get('TotalRevenue', revenue.get('totalRevenue', 0))))
            except:
                continue

    if not dates:
        if coin_purchases:
            for purchase in coin_purchases:
                date_str = purchase.get('Date', purchase.get('date', ''))
                if date_str:
                    try:
                        date = datetime.strptime(date_str, '%Y-%m-%d')
                        dates.append(date)
                        amounts.append(float(purchase.get('Revenue', purchase.get('revenue', 0))))
                    except:
                        continue

    if not dates:
        raise ValueError("No valid revenue data for chart")

    sorted_data = sorted(zip(dates, amounts), key=lambda x: x[0])
    dates, amounts = zip(*sorted_data)

    colors = ['#4ECDC4' if a > 0 else '#95E1D3' for a in amounts]
    bars = ax1.bar(range(len(dates)), amounts, color=colors, alpha=0.7)

    ax1.set_xlabel('Дата', fontsize=12)
    ax1.set_ylabel('Доход (€)', fontsize=12)
    ax1.set_title('Ежедневный доход', fontsize=14, fontweight='bold')

    step = max(1, len(dates) // 10)
    ax1.set_xticks(range(0, len(dates), step))
    ax1.set_xticklabels([d.strftime('%d.%m') for i, d in enumerate(dates) if i % step == 0],
                        rotation=45)

    for i, (bar, amount) in enumerate(zip(bars, amounts)):
        if amount > 0:
            height = bar.get_height()
            ax1.text(bar.get_x() + bar.get_width() / 2., height,
                     f'{amount:.1f}€',
                     ha='center', va='bottom', fontsize=8)

    cumulative = []
    total = 0
    for amount in amounts:
        total += amount
        cumulative.append(total)

    ax2.plot(range(len(dates)), cumulative, marker='o', linewidth=2,
             markersize=8, color='#6C5CE7')
    ax2.fill_between(range(len(dates)), cumulative, alpha=0.3, color='#A29BFE')

    ax2.set_xlabel('Дата', fontsize=12)
    ax2.set_ylabel('Накопленный доход (€)', fontsize=12)
    ax2.set_title('Накопленный доход', fontsize=14, fontweight='bold')

    # Настройка меток оси X для второго графика
    ax2.set_xticks(range(0, len(dates), step))
    ax2.set_xticklabels([d.strftime('%d.%m') for i, d in enumerate(dates) if i % step == 0],
                        rotation=45)

    if cumulative:
        ax2.annotate(f'Итого: {cumulative[-1]:.2f}€',
                     xy=(len(dates) - 1, cumulative[-1]),
                     xytext=(10, 10),
                     textcoords='offset points',
                     bbox=dict(boxstyle='round,pad=0.5', fc='yellow', alpha=0.5),
                     fontsize=10,
                     fontweight='bold')

    ax1.grid(True, alpha=0.3)
    ax2.grid(True, alpha=0.3)

    plt.tight_layout()

    temp_file = tempfile.NamedTemporaryFile(suffix='.png', delete=False)
    plt.savefig(temp_file.name, dpi=100, bbox_inches='tight')
    plt.close()

    return temp_file.name


async def generate_feature_usage_chart(features_data: List[Dict]) -> str:

    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(14, 7))

    features = []
    usage_counts = []
    coin_amounts = []

    for feature in features_data[:8]:
        features.append(feature.get('Feature', 'Unknown'))
        usage_counts.append(feature.get('UsageCount', 0))
        coin_amounts.append(feature.get('TotalCoins', 0))

    colors = plt.cm.Set3(range(len(features)))
    wedges, texts, autotexts = ax1.pie(usage_counts,
                                       labels=features,
                                       autopct='%1.1f%%',
                                       colors=colors,
                                       startangle=90)

    ax1.set_title('Использование функций (по количеству)', fontsize=12, fontweight='bold')

    y_pos = range(len(features))
    ax2.barh(y_pos, coin_amounts, color=colors, alpha=0.8)
    ax2.set_yticks(y_pos)
    ax2.set_yticklabels(features)
    ax2.set_xlabel('Потрачено монет', fontsize=11)
    ax2.set_title('Расход монет по функциям', fontsize=12, fontweight='bold')

    for i, (feature, amount) in enumerate(zip(features, coin_amounts)):
        ax2.text(amount, i, f' {amount}', va='center', fontsize=9)

    plt.tight_layout()

    temp_file = tempfile.NamedTemporaryFile(suffix='.png', delete=False)
    plt.savefig(temp_file.name, dpi=100, bbox_inches='tight')
    plt.close()

    return temp_file.name


async def generate_user_activity_chart(activity_data: Dict) -> str:

    fig, ((ax1, ax2), (ax3, ax4)) = plt.subplots(2, 2, figsize=(12, 10))

    fig.suptitle('Статистика активности пользователей', fontsize=16, fontweight='bold')

    days = ['Пн', 'Вт', 'Ср', 'Чт', 'Пт', 'Сб', 'Вс']
    activity = activity_data.get('weeklyActivity', [10, 15, 12, 18, 20, 25, 22])

    ax1.bar(days, activity, color='#3498DB', alpha=0.7)
    ax1.set_xlabel('День недели')
    ax1.set_ylabel('Активность')
    ax1.set_title('Активность по дням недели')
    ax1.grid(True, alpha=0.3)

    hours = list(range(24))
    hourly_activity = activity_data.get('hourlyActivity',
                                        [5] * 6 + [10] * 6 + [15] * 6 + [8] * 6)

    ax2.plot(hours, hourly_activity, color='#E74C3C', linewidth=2)
    ax2.fill_between(hours, hourly_activity, alpha=0.3, color='#E74C3C')
    ax2.set_xlabel('Час')
    ax2.set_ylabel('Активность')
    ax2.set_title('Активность по часам')
    ax2.grid(True, alpha=0.3)

    dates = activity_data.get('growthDates', [])
    users = activity_data.get('growthUsers', [])

    if dates and users:
        ax3.plot(range(len(dates)), users, marker='o', color='#2ECC71', linewidth=2)
        ax3.set_xlabel('Период')
        ax3.set_ylabel('Пользователей')
        ax3.set_title('Рост пользовательской базы')
        ax3.grid(True, alpha=0.3)
    else:
        ax3.text(0.5, 0.5, 'Нет данных', ha='center', va='center', fontsize=14)
        ax3.set_title('Рост пользовательской базы')

    ax4.axis('off')
    stats_text = f"""
    Всего пользователей: {activity_data.get('totalUsers', 0)}
    Активных за 30 дней: {activity_data.get('activeUsers', 0)}
    С Telegram: {activity_data.get('telegramUsers', 0)}

    Средняя активность: {activity_data.get('avgActivity', 0):.1f}/день
    Пиковое время: {activity_data.get('peakTime', '14:00')}
    Конверсия: {activity_data.get('conversion', 0):.1f}%
    """

    ax4.text(0.1, 0.5, stats_text, ha='left', va='center', fontsize=11,
             bbox=dict(boxstyle='round,pad=0.5', facecolor='lightgray', alpha=0.3))
    ax4.set_title('Общая статистика')

    plt.tight_layout()

    temp_file = tempfile.NamedTemporaryFile(suffix='.png', delete=False)
    plt.savefig(temp_file.name, dpi=100, bbox_inches='tight')
    plt.close()

    return temp_file.name


async def generate_spending_chart(data: List[tuple]) -> str:
    daily_stats = []
    for row in data:
        daily_stats.append({
            'Date': row[0] if isinstance(row[0], str) else row[0].strftime('%Y-%m-%d'),
            'TotalSpent': row[1]
        })
    return await generate_spending_chart_from_server_data(daily_stats)


async def generate_revenue_chart(data: List[tuple]) -> str:
    daily_revenue = []
    for row in data:
        daily_revenue.append({
            'Date': row[0] if isinstance(row[0], str) else row[0].strftime('%Y-%m-%d'),
            'TotalRevenue': row[1]
        })
    return await generate_revenue_chart_from_server_data(daily_revenue, [])
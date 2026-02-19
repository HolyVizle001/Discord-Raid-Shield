import discord
from discord.ext import commands
import asyncio
from datetime import datetime, timedelta
from collections import defaultdict
import re
import os
from dotenv import load_dotenv

load_dotenv()

CONFIG = {
    'BOT_TOKEN': os.getenv('BOT_TOKEN', 'YOUR_BOT_TOKEN_HERE'),
    'ALERT_CHANNEL_ID': int(os.getenv('ALERT_CHANNEL_ID', 0)) if os.getenv('ALERT_CHANNEL_ID') else None,
    'RATE_LIMITS': {
        'MAX_MESSAGES': 5,
        'MAX_MENTIONS': 3,
        'MAX_LINKS': 2,
        'TIME_WINDOW': 5,
    },
    'ACTIONS': {
        'TIMEOUT_DURATION': 600,
        'DELETE_MESSAGES': True,
        'BAN_ON_SEVERE': True,
        'SEVERE_THRESHOLD': 10,
    },
    'IGNORED_ROLES': ['Moderator', 'Admin', 'Trusted'],
    'SUSPICIOUS_PATTERNS': [
        r'discord\.gg/[a-zA-Z0-9]+',
        r'free\s*nitro',
        r'@everyone|@here',
    ]
}

class RaidTracker:
    def __init__(self):
        self.user_activity = defaultdict(lambda: {
            'messages': [],
            'mentions': [],
            'links': [],
            'violations': 0
        })

    def _clean_old_entries(self, user_id, time_window):
        now = datetime.now()
        cutoff = now - timedelta(seconds=time_window)

        activity = self.user_activity[user_id]
        activity['messages'] = [t for t in activity['messages'] if t > cutoff]
        activity['mentions'] = [t for t in activity['mentions'] if t > cutoff]
        activity['links'] = [t for t in activity['links'] if t > cutoff]

    def record_message(self, user_id):
        time_window = CONFIG['RATE_LIMITS']['TIME_WINDOW']
        self._clean_old_entries(user_id, time_window)

        self.user_activity[user_id]['messages'].append(datetime.now())
        return len(self.user_activity[user_id]['messages'])

    def record_mentions(self, user_id, count=1):
        time_window = CONFIG['RATE_LIMITS']['TIME_WINDOW']
        self._clean_old_entries(user_id, time_window)

        self.user_activity[user_id]['mentions'].append(datetime.now())
        return len(self.user_activity[user_id]['mentions'])

    def record_link(self, user_id):
        time_window = CONFIG['RATE_LIMITS']['TIME_WINDOW']
        self._clean_old_entries(user_id, time_window)

        self.user_activity[user_id]['links'].append(datetime.now())
        return len(self.user_activity[user_id]['links'])

    def add_violation(self, user_id):
        self.user_activity[user_id]['violations'] += 1
        return self.user_activity[user_id]['violations']

    async def cleanup_task(self):
        while True:
            await asyncio.sleep(300)
            now = datetime.now()
            cutoff = now - timedelta(seconds=CONFIG['RATE_LIMITS']['TIME_WINDOW'])

            users_to_remove = []
            for user_id, activity in self.user_activity.items():
                if (not activity['messages'] and 
                    not activity['mentions'] and 
                    not activity['links']):
                    users_to_remove.append(user_id)

            for user_id in users_to_remove:
                del self.user_activity[user_id]

intents = discord.Intents.default()
intents.message_content = True
intents.members = True

bot = commands.Bot(command_prefix='!', intents=intents)
tracker = RaidTracker()

def has_ignored_role(member):
    return any(role.name in CONFIG['IGNORED_ROLES'] for role in member.roles)

def count_mentions(message):
    count = len(message.mentions) + len(message.role_mentions)
    if message.mention_everyone:
        count += 10
    return count

def count_links(content):
    url_pattern = r'https?://[^\s]+'
    matches = re.findall(url_pattern, content)
    return len(matches)

def has_suspicious_pattern(content):
    for pattern in CONFIG['SUSPICIOUS_PATTERNS']:
        if re.search(pattern, content, re.IGNORECASE):
            return True
    return False

async def send_alert(guild, user, reason, details):
    if not CONFIG['ALERT_CHANNEL_ID']:
        return

    alert_channel = guild.get_channel(CONFIG['ALERT_CHANNEL_ID'])
    if not alert_channel:
        return

    embed = discord.Embed(
        title='🚨 Raid Protection Alert',
        description=f'**User:** {user.mention} ({user.id})\n**Reason:** {reason}',
        color=discord.Color.red(),
        timestamp=datetime.now()
    )
    embed.add_field(name='Details', value=details, inline=False)

    try:
        await alert_channel.send(embed=embed)
    except Exception as e:
        print(f'Failed to send alert: {e}')

async def take_action(message, user, reason, violations):
    member = message.guild.get_member(user.id)
    if not member:
        return

    try:
        if CONFIG['ACTIONS']['DELETE_MESSAGES']:
            try:
                await message.delete()
            except:
                pass

        if CONFIG['ACTIONS']['BAN_ON_SEVERE'] and violations >= CONFIG['ACTIONS']['SEVERE_THRESHOLD']:
            if message.guild.me.guild_permissions.ban_members:
                await member.ban(reason=f'Raid Protection: {reason}')
                await send_alert(
                    message.guild, 
                    user, 
                    'User Banned',
                    f'Violations: {violations}\nReason: {reason}'
                )
                print(f'Banned user {user} for: {reason}')
        else:
            if message.guild.me.guild_permissions.moderate_members:
                timeout_duration = timedelta(seconds=CONFIG['ACTIONS']['TIMEOUT_DURATION'])
                await member.timeout(timeout_duration, reason=f'Raid Protection: {reason}')
                await send_alert(
                    message.guild,
                    user,
                    'User Timed Out',
                    f'Duration: {CONFIG["ACTIONS"]["TIMEOUT_DURATION"] / 60} minutes\nReason: {reason}'
                )
                print(f'Timed out user {user} for: {reason}')

    except discord.Forbidden:
        print(f'Missing permissions to moderate {user}')
    except Exception as e:
        print(f'Failed to take action: {e}')

@bot.event
async def on_ready():
    print(f'✅ Logged in as {bot.user}')
    print('🛡️  Raid Protection Active')
    print(f'📊 Rate Limits: {CONFIG["RATE_LIMITS"]["MAX_MESSAGES"]} msgs, '
          f'{CONFIG["RATE_LIMITS"]["MAX_MENTIONS"]} mentions, '
          f'{CONFIG["RATE_LIMITS"]["MAX_LINKS"]} links per '
          f'{CONFIG["RATE_LIMITS"]["TIME_WINDOW"]}s')

    bot.loop.create_task(tracker.cleanup_task())

@bot.event
async def on_message(message):
    if message.author.bot or not message.guild:
        return

    member = message.guild.get_member(message.author.id)
    if not member or has_ignored_role(member):
        return

    user_id = message.author.id
    violated = False
    reason = ''

    message_count = tracker.record_message(user_id)
    if message_count > CONFIG['RATE_LIMITS']['MAX_MESSAGES']:
        violated = True
        reason = f'Spam: {message_count} messages in {CONFIG["RATE_LIMITS"]["TIME_WINDOW"]}s'

    mention_count = count_mentions(message)
    if mention_count > 0:
        total_mentions = tracker.record_mentions(user_id, mention_count)
        if total_mentions > CONFIG['RATE_LIMITS']['MAX_MENTIONS']:
            violated = True
            reason = f'Mention spam: {total_mentions} mentions in {CONFIG["RATE_LIMITS"]["TIME_WINDOW"]}s'

    link_count = count_links(message.content)
    if link_count > 0:
        total_links = tracker.record_link(user_id)
        if total_links > CONFIG['RATE_LIMITS']['MAX_LINKS']:
            violated = True
            reason = f'Link spam: {total_links} links in {CONFIG["RATE_LIMITS"]["TIME_WINDOW"]}s'

    if has_suspicious_pattern(message.content):
        violated = True
        reason = 'Suspicious content pattern detected'

    if violated:
        violations = tracker.add_violation(user_id)
        await take_action(message, message.author, reason, violations)

    await bot.process_commands(message)

@bot.command(name='raidstats')
@commands.has_permissions(moderate_members=True)
async def raid_stats(ctx):
    active_users = len(tracker.user_activity)
    total_violations = sum(data['violations'] for data in tracker.user_activity.values())

    embed = discord.Embed(
        title='🛡️ Raid Protection Statistics',
        color=discord.Color.blue()
    )
    embed.add_field(name='Tracked Users', value=str(active_users), inline=True)
    embed.add_field(name='Total Violations', value=str(total_violations), inline=True)
    embed.add_field(
        name='Rate Limits',
        value=f'Messages: {CONFIG["RATE_LIMITS"]["MAX_MESSAGES"]}\n'
              f'Mentions: {CONFIG["RATE_LIMITS"]["MAX_MENTIONS"]}\n'
              f'Links: {CONFIG["RATE_LIMITS"]["MAX_LINKS"]}\n'
              f'Window: {CONFIG["RATE_LIMITS"]["TIME_WINDOW"]}s',
        inline=False
    )

    await ctx.send(embed=embed)

@bot.command(name='checkuser')
@commands.has_permissions(moderate_members=True)
async def check_user(ctx, member: discord.Member):
    user_id = member.id

    if user_id not in tracker.user_activity:
        await ctx.send(f'{member.mention} has no recent activity.')
        return

    activity = tracker.user_activity[user_id]

    embed = discord.Embed(
        title=f'Activity for {member}',
        color=discord.Color.blue()
    )
    embed.add_field(name='Recent Messages', value=str(len(activity['messages'])), inline=True)
    embed.add_field(name='Recent Mentions', value=str(len(activity['mentions'])), inline=True)
    embed.add_field(name='Recent Links', value=str(len(activity['links'])), inline=True)
    embed.add_field(name='Total Violations', value=str(activity['violations']), inline=True)

    await ctx.send(embed=embed)

@bot.command(name='resetuser')
@commands.has_permissions(moderate_members=True)
async def reset_user(ctx, member: discord.Member):
    user_id = member.id

    if user_id in tracker.user_activity:
        del tracker.user_activity[user_id]
        await ctx.send(f'✅ Reset activity tracking for {member.mention}')
    else:
        await ctx.send(f'{member.mention} has no tracked activity.')

@bot.event
async def on_command_error(ctx, error):
    if isinstance(error, commands.MissingPermissions):
        await ctx.send('❌ You do not have permission to use this command.')
    elif isinstance(error, commands.MemberNotFound):
        await ctx.send('❌ Member not found.')
    else:
        print(f'Error: {error}')

if __name__ == '__main__':
    if CONFIG['BOT_TOKEN'] == 'YOUR_BOT_TOKEN_HERE' or not CONFIG['BOT_TOKEN']:
        print('❌ Error: BOT_TOKEN not set!')
        print('Please set your bot token in the .env file or CONFIG dictionary')
        exit(1)

    bot.run(CONFIG['BOT_TOKEN'])

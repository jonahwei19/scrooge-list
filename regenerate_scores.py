import json

# Load the data
with open('/tmp/scrooge-list/scrooge_data_v3.json', 'r') as f:
    data = json.load(f)

# Recalculate scrooge scores
for entry in data:
    nw = entry.get('net_worth_billions', 0)
    lf = entry.get('liquidity_factor', 0.4)
    giving = entry.get('total_lifetime_giving_millions', 0)
    
    # Skip entries with 0 net worth (duplicates/deceased)
    if nw <= 0:
        entry['scrooge_score'] = 0
        entry['giving_rate_pct'] = 0
        continue
    
    # Calculate deployable wealth in millions
    deployable = nw * 1000 * lf  # Convert billions to millions, apply liquidity
    
    if deployable > 0:
        giving_ratio = giving / deployable
        # Cap at 0-100
        scrooge_score = max(0, min(100, 100 * (1 - giving_ratio)))
        giving_rate_pct = (giving_ratio * 100)
    else:
        scrooge_score = 100
        giving_rate_pct = 0
    
    entry['scrooge_score'] = round(scrooge_score, 2)
    entry['giving_rate_pct'] = round(giving_rate_pct, 4)

# Save updated data
with open('/tmp/scrooge-list/scrooge_data_v3.json', 'w') as f:
    json.dump(data, f, indent=2)

# Create website version (filter positive NW, sort by scrooge score desc)
website_data = [e for e in data if e.get('net_worth_billions', 0) > 0]
website_data.sort(key=lambda x: x.get('scrooge_score', 0), reverse=True)

with open('/tmp/scrooge-list/docs/scrooge_latest.json', 'w') as f:
    json.dump(website_data, f, indent=2)

print(f"Processed {len(data)} entries")
print(f"Website data: {len(website_data)} entries (positive NW)")
print("\nTop 10 Scrooges:")
for i, e in enumerate(website_data[:10]):
    print(f"  {i+1}. {e['name']}: {e['scrooge_score']} (${e['total_lifetime_giving_millions']}M / ${e['net_worth_billions']}B)")
print("\nTop 10 Givers:")
for i, e in enumerate(sorted(website_data, key=lambda x: x.get('scrooge_score', 0))[:10]):
    print(f"  {i+1}. {e['name']}: {e['scrooge_score']} (${e['total_lifetime_giving_millions']}M / ${e['net_worth_billions']}B)")

import pandas as pd
import requests
import json
from bs4 import BeautifulSoup
from datetime import datetime

# 🔹 Load Event export
events = pd.read_csv("Event export.csv").dropna(how="all")

# Extract AppName + AppNumber
events[['AppName','AppNumber']] = events['Target'].str.extract(r'Application:(.*?) \[(AL\d+)\]', expand=True)

# Filter only rows where Name is "Create App Passed" and Status is PASSED/FAILED
events = events[
    (events['Name'] == "Create App Passed") &
    (events['Status'].isin(["PASSED", "FAILED"]))
]

# Rename Status to avoid conflicts after merge
events = events.rename(columns={"Status":"EventStatus"})

# 🔹 Load CMDB and clean headers
cmdb = pd.read_excel("CMDB.xlsx")
cmdb.columns = cmdb.columns.str.strip()  # remove accidental spaces

# Merge Event export with CMDB on AppNumber
final = pd.merge(events, cmdb, left_on="AppNumber", right_on="NUMBER", how="left")

# Flag mismatches
def flag_row(x):
    if x['EventStatus'] == "FAILED":
        return "RED"
    elif pd.isna(x['NAME']) and x['EventStatus'] == "PASSED":
        return "YELLOW"
    else:
        return ""
final['Flag'] = final.apply(flag_row, axis=1)

# Summary counts
total_passed = len(final[final['EventStatus']=="PASSED"])
total_failed = len(final[final['EventStatus']=="FAILED"])
total_mismatch = len(final[final['Flag']=="YELLOW"])

# Timestamp
last_updated = datetime.now().strftime("%d-%b-%Y %H:%M IST")

summary_html = f"""
<h2>Reconciliation Summary</h2>
<ul>
  <li><b>Total PASSED:</b> {total_passed}</li>
  <li><b>Total FAILED:</b> {total_failed}</li>
  <li><b>Total Mismatches (Yellow):</b> {total_mismatch}</li>
  <li><b>Last Updated:</b> {last_updated}</li>
</ul>
"""

# 🔹 Confluence API details
page_id = "327681"  # Published page ID
confluence_url = f"https://varah6210.atlassian.net/wiki/rest/api/content/{page_id}?expand=body.storage,version"
headers = {"Content-Type":"application/json"}
auth = ("varah6210@gmail.com","ATATT3xFfGF0uwwDRMVNIqU4CvM6pQc6m1939i_--mnH0ZtZ_L0WqmyDlTffhu-Y8FNz9-OoaXT8sOpIOpQQ6xickn67S07qf_s47aa5ty_zCbjrXdKEeCL00wfqlfyOa7yMK5HKNTJmiPXcAUoExx5EHKe1Iqr1axuEdUbQWYjsISJlphBSqBw=CCB41692")

# Step 1: Get existing page content
resp = requests.get(confluence_url, headers=headers, auth=auth)
page = resp.json()

# Safe fallback for version
version_info = page.get("version", {})
version_number = version_info.get("number", 1) + 1
existing_content = page.get("body", {}).get("storage", {}).get("value", "")

# Parse existing HTML
soup = BeautifulSoup(existing_content, "html.parser")

# Step 2: Update or append rows with color coding
table = soup.find("table")
if not table:
    table = soup.new_tag("table", attrs={"class":"confluenceTable"})
    soup.append(table)

# ✅ Safe fallback for missing columns
expected_cols = [
    'Created','AppNumber','NAME','EventStatus',
    'Business Owner','Email','Technical Owner','Technical Owner Email','Support Group'
]

for _, row in final.iterrows():
    app_number = row.get('AppNumber', None)
    updated = False

    for tr in table.find_all("tr"):
        if app_number and (app_number in tr.text):
            tds = tr.find_all("td")
            if row['Flag'] == "YELLOW":
                for td in tds:
                    td['style'] = "background-color:yellow;"
            elif row['Flag'] == "RED":
                for td in tds:
                    td['style'] = "background-color:red; color:white;"
            if len(tds) >= 9:
                # Safe fallback: only update if column exists
                tds[4].string = str(row.get('Business Owner', ''))
                tds[5].string = str(row.get('Email', ''))
                tds[6].string = str(row.get('Technical Owner', ''))
                tds[7].string = str(row.get('Technical Owner Email', ''))
                tds[8].string = str(row.get('Support Group', ''))
            updated = True
            break

    if not updated:
        new_row_html = "<tr>"
        for col in expected_cols:
            val = str(row[col]) if col in row and pd.notna(row[col]) else ""
            style = ""
            if row['Flag'] == "YELLOW":
                style = " style='background-color:yellow;'"
            elif row['Flag'] == "RED":
                style = " style='background-color:red; color:white;'"
            new_row_html += f"<td{style}>{val}</td>"
        new_row_html += "</tr>"
        table.append(BeautifulSoup(new_row_html, "html.parser"))

# Step 3: Append summary + updated table below existing content
new_content = existing_content + "<hr/>" + summary_html + str(soup)

payload = {
    "id": page.get("id", page_id),
    "type": page.get("type", "page"),
    "title": page.get("title", "Untitled"),
    "body": {
        "storage": {
            "value": new_content,
            "representation": "storage"
        }
    },
    "version": {"number": version_number}
}

update_url = f"https://varah6210.atlassian.net/wiki/rest/api/content/{page_id}"
resp_update = requests.put(update_url, headers=headers, auth=auth, data=json.dumps(payload))

print("Update status:", resp_update.status_code)
print("Response:", resp_update.text[:300])

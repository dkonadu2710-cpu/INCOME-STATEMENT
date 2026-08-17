# PCG Hobor Church Financial Reporting App

## Platform Recommendation

**Recommended: Flask Web Application (Python)**

### Why This Platform?

1. **Low/No Cost**: Flask is free and open-source. SQLite database is free and requires no separate server setup.

2. **Cross-Platform Access**: Works on any device with a web browser - phones, tablets, laptops, desktops. No installation needed on client devices.

3. **Simple for Non-Technical Users**: Clean, intuitive web interface with forms and buttons. No spreadsheet formulas to break.

4. **Offline Capability Consideration**: While this web app requires internet connectivity, the data is stored locally in a SQLite database file that can be backed up easily. For truly offline capability, you would need a more complex setup (like Progressive Web App or native mobile app), which increases cost and complexity significantly.

5. **Role-Based Access Control**: Built-in user authentication with Admin and Treasurer roles.

6. **Audit Trail**: Every action is logged for accountability.

7. **Professional PDF Reports**: Generate clean, printable reports suitable for church records.

8. **Easy Deployment**: Can be hosted on free/low-cost platforms like PythonAnywhere, Heroku, or run locally on a church computer.

### Alternative Options Considered:

- **Spreadsheet (Google Sheets/Excel)**: Too error-prone, difficult to implement approval workflow, no proper audit trail, formulas can be accidentally broken.
- **Mobile App**: Higher development cost, requires app store deployment, harder to maintain.
- **Full-stack frameworks (Django, etc.)**: Overkill for this use case, steeper learning curve.

---

## Getting Started

### Installation & Running Locally

1. **Ensure Python 3 is installed** (Python 3.8+)

2. **Install dependencies**:
   ```bash
   pip install flask flask-sqlalchemy flask-login flask-wtf wtforms email-validator reportlab passlib
   ```

3. **Run the application**:
   ```bash
   python app.py
   ```

4. **Access the app**: Open your browser and go to `http://localhost:5000`

### Default Login Credentials

- **Username**: `admin`
- **Password**: `admin123`

**IMPORTANT**: Change the admin password immediately after first login!

---

## User Guide

### For Admin (Catechist)

#### First-Time Setup

1. **Log in** with the default admin credentials
2. **Change your password** (recommended immediately)
3. **Create treasurer accounts**:
   - Go to "Users" → "Add New User"
   - Enter username, full name, password
   - Select role: "Treasurer"
   - Check "Active" to enable the account
   - Click "Create User"

4. **Review/Edit Categories** (optional):
   - Go to "Categories" to see income/expenditure categories
   - Add new categories or edit existing ones as needed

#### Daily Operations

1. **View Dashboard**: See current balances, pending approvals, recent activity

2. **Review Pending Sessions**:
   - Sessions submitted by treasurers appear under "Pending Approvals"
   - Click "Review" to examine the session details
   - Verify opening balances, income, and expenditure entries
   - **Approve** if correct, or **Reject** with comments if corrections needed

3. **Generate Reports**:
   - **Daily Report**: View any session and click "Download PDF"
   - **Periodic Summary**: Go to "Reports" → select date range → "Generate Report"

4. **Manage Sessions**:
   - Reopen approved sessions if corrections are needed (with audit trail)
   - View all sessions with filters (status, date range)

5. **Monitor Activity**:
   - Check "Audit Log" to see who did what and when
   - Track all creates, edits, submissions, approvals, and rejections

---

### For Treasurers/Data-Entry Clerks

#### Creating a Session Report

1. **Log in** with your credentials

2. **Start a New Session**:
   - Click "New Session" from Dashboard or Sessions page
   - Enter the session date (e.g., Sunday's date)
   - Opening balances may be auto-filled from the previous approved session
   - Click "Create Session"

3. **Add Transactions**:
   - **For each income item**:
     - Select Type: "Income"
     - Choose Category (Offertory, Tithe, Thanksgiving, etc.)
     - Enter Description (optional notes)
     - Enter Amount in GHS
     - Select Fund (Mobile Money, Bank, or Cash)
     - Click "Add Transaction"
   
   - **For each expenditure item**:
     - Select Type: "Expenditure"
     - Choose Category (Utilities, Stationery, Transport, etc.)
     - Enter Description
     - Enter Amount
     - Select Fund
     - Click "Add Transaction"

4. **Review Summary**:
   - Check the calculated totals and closing balances
   - Closing Balance = Opening Balance + Income - Expenditure (per fund)

5. **Submit for Approval**:
   - When all transactions are entered, click "Submit for Approval"
   - The session status changes to "Submitted"
   - You can no longer edit it until the admin approves or rejects it

#### After Submission

- **If Approved**: Session is locked and becomes part of official records
- **If Rejected**: 
  - You'll see the admin's rejection reason
  - Click "Edit and Resubmit" to make corrections
  - Fix the issues and submit again

#### Viewing Your Reports

- Go to "Sessions" to see all your submitted reports
- Filter by status to find drafts, submitted, approved, or rejected sessions
- Click "View" to see details or "Download PDF" for a printable copy

---

## Features Overview

### Core Functionality

✅ **Session-based reporting** (daily/Sunday)  
✅ **Three funds tracking**: Mobile Money, Bank, Cash  
✅ **Automatic balance calculations** (no manual math errors)  
✅ **Balance roll-forward**: Closing balance of one session becomes opening balance of next  
✅ **Income & Expenditure categorization**  
✅ **Approval workflow**: Draft → Submitted → Approved/Rejected  
✅ **PDF export** with professional formatting  
✅ **Periodic summary reports** (weekly, monthly, quarterly, yearly, custom)  

### Security & Accountability

✅ **User authentication** (username/password)  
✅ **Role-based access** (Admin vs. Treasurer)  
✅ **Complete audit trail** of all actions  
✅ **Session locking** after approval  
✅ **Rejection with comments** for quality control  

### Admin Controls

✅ **User management** (create/edit/deactivate users)  
✅ **Category management** (add/edit income/expenditure categories)  
✅ **Session reopening** (with audit trail)  
✅ **Dashboard monitoring** (pending approvals, current balances, activity log)  

---

## Data Backup

The database is stored in a single file: `pcg_hobor_finance.db`

**To backup**: Simply copy this file to a safe location (USB drive, cloud storage, etc.)

**To restore**: Replace the database file with your backup copy.

**Recommendation**: Backup weekly or after important sessions.

---

## Troubleshooting

### Common Issues

1. **"Invalid username or password"**
   - Check caps lock
   - Ensure your account is active (contact admin if unsure)

2. **"Cannot edit this session"**
   - Sessions can only be edited in "Draft" or "Rejected" status
   - Submitted sessions must be rejected by admin first
   - Approved sessions require admin to reopen them

3. **"Opening balance doesn't match previous closing"**
   - The system auto-fills from the last *approved* session
   - If there's no approved session, enter manually
   - Admin can override if needed for corrections

4. **App won't start**
   - Ensure all dependencies are installed
   - Check if port 5000 is already in use
   - Try: `python app.py` and check error messages

---

## Support & Customization

For modifications or additional features, the codebase is structured for easy extension:

- **Models**: `app.py` lines 40-150 (database structure)
- **Routes**: `app.py` lines 250-750 (URL endpoints)
- **Templates**: `templates/` folder (HTML pages)
- **Categories**: Managed through the app's admin interface

---

## License

This application was built specifically for Presbyterian Church of Ghana, Hobor.

---

**Built with ❤️ for PCG Hobor**

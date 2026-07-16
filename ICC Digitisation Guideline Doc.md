# **OIA Project Intelligence Platform**

## **Vision Document (Version 2.0)**

### **Project Overview**

The OIA Project Intelligence Platform is a centralized web-based system designed to manage, track, analyze, and report on all ICC and IGP projects conducted under the Office of International Affairs (OIA), Christ University.

The platform serves as the operational source of truth for project execution, volunteer involvement, buddy management, attendance, documentation, feedback, reporting, and analytics.

The platform is designed to provide transparency, institutional memory, operational efficiency, and data-driven decision-making while ensuring continuity across annual leadership transitions.

---

# **Strategic Objectives**

### **Project Visibility**

Provide complete visibility into all ICC and IGP projects across campuses.

### **Operational Efficiency**

Reduce manual effort involved in attendance tracking, volunteer coordination, buddy management, reporting, and analytics.

### **Institutional Memory**

Preserve project documentation, attendance records, volunteer contributions, feedback, reports, and historical insights.

### **Reporting Automation**

Generate project, monthly, and annual reports directly from operational data.

### **Analytics & Decision Support**

Provide interactive dashboards and drill-down analytics for faculty and student leadership.

---

# **Platform Scope**

The platform shall exclusively track project-related activities.

Included Scope:

* ICC Projects  
* IGP Projects  
* Volunteers  
* Buddy Programs  
* Attendance  
* Feedback  
* Documents  
* Reports  
* Analytics

Excluded Scope:

* FRRO  
* Visa tracking  
* Academic administration  
* Student services  
* Personal student records  
* Non-project operations

---

# **Core Information Architecture**

The entire platform shall follow a project-centric hierarchy.

Campus  
→ Program Type  
→ Project  
→ Project Components

Program Types:

* ICC  
* IGP

Examples:

Bannerghatta Campus  
→ ICC  
→ Sports Day

Bannerghatta Campus  
→ ICC  
→ Leadership Camp

Bannerghatta Campus  
→ IGP  
→ University of Cincinnati Program

Bannerghatta Campus  
→ IGP  
→ France Exchange Program

All operational records must belong to a project.

---

# **User Roles**

## **Faculty**

Permissions:

* Full platform visibility  
* Analytics access  
* Reporting access  
* Attendance verification  
* Project oversight

---

## **ICC Core Committee**

Permissions:

* Project administration  
* Volunteer management  
* Buddy management  
* Reporting access  
* Analytics access

---

## **Volunteers**

Permissions:

* Registration  
* Contribution logging  
* Participation tracking

---

## **Buddies**

Permissions:

* Buddy activity logging  
* Assigned participant tracking  
* Feedback submission

---

## **Exchange Students**

Permissions:

* Feedback submission  
* Experience sharing  
* Limited project access

---

# **Core Modules**

## **Module 1: Project Management**

Track all ICC and IGP projects.

Stores:

* Campus  
* Program Type  
* Project Details  
* Project Timeline  
* Project Status

---

## **Module 2: Attendance Verification**

Track verified attendance.

Stores:

* Participant  
* Project  
* Project Day  
* Attendance Status  
* Verified By  
* Timestamp

Attendance and contributions remain independent systems.

---

## **Module 3: Volunteer Management**

Track:

* Volunteer registrations  
* Skills  
* Interests  
* Project assignments  
* Contribution history

---

## **Module 4: Buddy Management**

Track:

* Buddy applications  
* Buddy assignments  
* Buddy logs  
* Interaction records

---

## **Module 5: Contribution Logging**

Track:

* Volunteer activities  
* Buddy activities  
* Media support  
* Event support  
* Logistics support

All contributions require project association.

---

## **Module 6: Feedback System**

Track:

* Event feedback  
* IGP feedback  
* Buddy feedback  
* Experience sharing

---

## **Module 7: Document Repository**

Store references to:

* Posters  
* Reports  
* Presentations  
* Photos  
* Videos

Files remain in Google Drive.

The platform stores metadata and links only.

---

## **Module 8: Reporting Engine**

Generate:

### **Project Reports**

Project-specific operational reports.

### **Monthly Reports**

Monthly OIA activity summaries.

### **Academic Year Reports**

Year-end operational reports and impact summaries.

---

## **Module 9: Analytics Platform**

Provide interactive analytics.

Supported Filters:

* Campus  
* Program Type  
* Project  
* Date Range  
* Country  
* Volunteer  
* Buddy

Required Drilldown:

All Campuses  
→ Campus  
→ ICC / IGP  
→ Project  
→ Project Day  
→ Individual Records

---

# **Registration Model**

Users register directly.

Workflow:

Register  
→ Pending Approval  
→ Approved / Rejected  
→ Role Assignment

No dependency on preloaded student databases.

---

# **Mobile Strategy**

The platform shall be developed as a responsive web application.

Future roadmap:

Responsive Web App  
→ Progressive Web App (PWA)  
→ Optional Mobile App Packaging

The platform shall maintain a single codebase.

---

# **Success Criteria**

The platform shall provide:

* Centralized project visibility  
* Reliable attendance records  
* Volunteer tracking  
* Buddy tracking  
* Automated reporting  
* Interactive analytics  
* Institutional memory  
* Faculty decision support  
* Cross-campus project visibility  
* Leadership continuity

The platform shall function as the primary operational intelligence system for ICC and IGP activities within the Office of International Affairs.


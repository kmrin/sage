# Privacy Policy - Sage

### Last updated: `20/10/2026`

## Overview

This Privacy Policy explains how Sage (the "Bot", user ID `1442149692992393306`) processes limited information from Discord servers and users.
By inviting or using Sage, you consent to the collection and use of data as described in this Privacy Policy.

## Data Controller
If you have privacy-related questions, please contact the developer through the contact methods shown in the
[Terms of Service](https://github.com/kmrin/sage/blob/main/sage/assets/docs/terms_of_service.md).

## Data Collected
Sage stores **only metadata necessary for its features**, specifically:
* **Server data**: Name, ID, member count, role names, role IDs and icon URL.
* **User data (per server)**: List of all members including their global name, display name, ID and avatar URL.

Sage does **not** store message content or any other personal data beyond what is described above, except transiently in memory as required to respond to commands.

## Purpose of Data Processing
The data listed above is used **only** for tracking the state of features that rely on user or role metadata.

## Data Storage and Security
All stored data is kept in a **PostgreSQL database** located on the machine that hosts Sage.

The database is intended to be accessible **only** to the Sage process and server operator, and is not exposed to the public internet by design.

Reasonable technical and organizational measures should be taken by the host operator (you) to secure the environment (for example, firewalling the database and limiting access to the host machine.)

## Data Sharing
Sage does **not** share stored server or user metadata with any third parties.

However, when using commands to call external APIs (e.g., image or text generation, random images), Sage may send limited request information (such as keywords and command parameters) to those APIs to fulfill the user's request.
Subject to each provider's own privacy policy.

## Data Retention
Sage retains stored server and user metadata only as long as necessary to provide its features.
When Sage is removed from a server, or when the host operator desides to reset data, stored metadata for that server and its members will be deleted from the database by design.

## User Rights and Server Control
Individual Discord users who have questions about how Sage operates on a specific server should contact the server's administrators first.
Server owners and administrators may request deletion of their server's stored metadata at any time by contacting the host or by following any documented reset/deletion commands provided by Sage.

## Children's Privacy
Sage does not knowngly target or profile children; it operates within Discord and relies on Discord's own age restrictions and policies.
If you believe that Sage is storing information in a way that violates applicable child privacy laws, please contact the developer so the issue can be investigated and addressed as soon as possible.

## Changes to this Policy
This privacy policy may be updated from time to time to reflect changes in Sage's functionality or legal requirements. 
Material changes should be announced via the project repository or other appropriate channels, and continued use of Sage after updates indicates acceptance of the revised Policy.
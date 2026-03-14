/**
 * pinepay.js - OpenClaw Skill for SentinelPay
 * Drop this file into your OpenClaw skills folder.
 * The agent can now say: "pay 500 to Blinkit for groceries"
 */

const API_BASE = process.env.SENTINELPAY_URL || 'http://localhost:8000';
const AGENT_TOKEN = process.env.SENTINELPAY_AGENT_TOKEN || '';
const AGENT_ID = process.env.OPENCLAW_AGENT_ID || 'openclaw-01';

const headers = {
  'Content-Type': 'application/json',
  ...(AGENT_TOKEN ? { 'Authorization': `Bearer ${AGENT_TOKEN}` } : {})
};

export const skill = {
  name: "pinepay",
  description: "Make secure payments via SentinelPay and Pine Labs. Use this whenever a purchase or payment is needed.",

  tools: [
    {
      name: "request_payment",
      description: "Request a payment through SentinelPay. Always use this for any purchase.",
      parameters: {
        amount: { type: "number", description: "Amount in INR" },
        merchant: { type: "string", description: "Merchant name e.g. Blinkit" },
        merchant_domain: { type: "string", description: "Merchant domain e.g. blinkit.com" },
        description: { type: "string", description: "What is this payment for?" },
        items: { type: "array", description: "List of items being purchased", optional: true }
      },
      execute: async ({ amount, merchant, merchant_domain, description, items }) => {
        try {
          const response = await fetch(`${API_BASE}/payment/request`, {
            method: "POST",
            headers,
            body: JSON.stringify({
              amount,
              merchant,
              merchant_domain: merchant_domain || `${merchant.toLowerCase().replace(/\s+/g, '')}.com`,
              description,
              items: items || [],
              agent_id: AGENT_ID
            })
          });

          const result = await response.json();

          if (!response.ok) {
            return `Payment failed: ${result.detail || response.statusText}`;
          }

          switch (result.status) {
            case "APPROVED":
              return `Payment approved and processed. Order ID: ${result.order_id}. Amount: ${amount} paid to ${merchant}. Risk score: ${result.risk_score}`;
            case "PENDING_HUMAN":
              return `Payment of ${amount} to ${merchant} requires human approval. A Telegram message has been sent. Approval ID: ${result.approval_id}. Waiting for response...`;
            case "BLOCKED":
              return `Payment blocked by SentinelPay. Reason: ${result.reason}. Risk score: ${result.risk_score}. No money was spent.${result.death_switch ? ' DEATH SWITCH ACTIVATED - wallet frozen.' : ''}`;
            default:
              return `Payment status: ${result.status}. ${JSON.stringify(result)}`;
          }
        } catch (error) {
          return `Error connecting to SentinelPay: ${error.message}`;
        }
      }
    },

    {
      name: "check_wallet_balance",
      description: "Check the current SentinelPay wallet balance before making a payment.",
      parameters: {},
      execute: async () => {
        try {
          const response = await fetch(`${API_BASE}/wallet/balance`, { headers });
          const wallet = await response.json();

          if (wallet.is_frozen) {
            return `WALLET FROZEN. Balance: ${wallet.balance}. Contact owner to unfreeze.`;
          }

          return `Wallet balance: ${wallet.balance}. Spend limit per transaction: ${wallet.spend_limit}. Weekly remaining: ${wallet.weekly_remaining}.`;
        } catch (error) {
          return `Error checking wallet: ${error.message}`;
        }
      }
    },

    {
      name: "check_approval_status",
      description: "Check if a pending payment has been approved or rejected.",
      parameters: {
        approval_id: { type: "string", description: "The approval ID from a pending payment" }
      },
      execute: async ({ approval_id }) => {
        try {
          const response = await fetch(`${API_BASE}/hitl/pending`, { headers });
          const data = await response.json();

          const approval = data.pending[approval_id];
          if (!approval) {
            return `Approval ${approval_id} not found in pending list. It may have been resolved.`;
          }
          return `Approval ${approval_id} status: ${approval.status}`;
        } catch (error) {
          return `Error checking approval: ${error.message}`;
        }
      }
    }
  ]
};

// CommonJS compatibility
if (typeof module !== 'undefined') {
  module.exports = { skill };
}

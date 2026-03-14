package skills

import (
	"bytes"
	"encoding/json"
	"fmt"
	"net/http"
	"os"
	"time"
)

type PaymentRequest struct {
	Amount         float64  `json:"amount"`
	Merchant       string   `json:"merchant"`
	MerchantDomain string   `json:"merchant_domain"`
	Description    string   `json:"description"`
	AgentID        string   `json:"agent_id"`
	Items          []string `json:"items,omitempty"`
}

type PaymentResult struct {
	Status        string  `json:"status"`
	TransactionID string  `json:"transaction_id"`
	OrderID       string  `json:"order_id"`
	Amount        float64 `json:"amount"`
	Merchant      string  `json:"merchant"`
	RiskScore     float64 `json:"risk_score"`
	Reason        string  `json:"reason"`
	Message       string  `json:"message"`
}

type WalletBalance struct {
	Balance        float64 `json:"balance"`
	SpendLimit     float64 `json:"spend_limit"`
	WeeklyRemaining float64 `json:"weekly_remaining"`
	IsFrozen       bool    `json:"is_frozen"`
}

func getConfig() (string, string) {
	baseURL := os.Getenv("SENTINELPAY_URL")
	if baseURL == "" {
		baseURL = "http://localhost:8000"
	}
	token := os.Getenv("SENTINELPAY_AGENT_TOKEN")
	return baseURL, token
}

func RequestPayment(amount float64, merchant, domain, description string) (string, error) {
	baseURL, token := getConfig()

	req := PaymentRequest{
		Amount:         amount,
		Merchant:       merchant,
		MerchantDomain: domain,
		Description:    description,
		AgentID:        os.Getenv("PICOCLAW_AGENT_ID"),
	}
	if req.AgentID == "" {
		req.AgentID = "picoclaw-01"
	}

	body, err := json.Marshal(req)
	if err != nil {
		return "", fmt.Errorf("failed to marshal request: %w", err)
	}

	httpReq, err := http.NewRequest("POST", baseURL+"/payment/request", bytes.NewBuffer(body))
	if err != nil {
		return "", fmt.Errorf("failed to create request: %w", err)
	}
	httpReq.Header.Set("Content-Type", "application/json")
	if token != "" {
		httpReq.Header.Set("Authorization", "Bearer "+token)
	}

	client := &http.Client{Timeout: 30 * time.Second}
	resp, err := client.Do(httpReq)
	if err != nil {
		return "", fmt.Errorf("request failed: %w", err)
	}
	defer resp.Body.Close()

	var result PaymentResult
	if err := json.NewDecoder(resp.Body).Decode(&result); err != nil {
		return "", fmt.Errorf("failed to decode response: %w", err)
	}

	switch result.Status {
	case "APPROVED":
		return fmt.Sprintf("Payment approved. Order: %s. %.2f paid to %s.",
			result.OrderID, amount, merchant), nil
	case "PENDING_HUMAN":
		return fmt.Sprintf("Payment of %.2f to %s pending your approval on Telegram.",
			amount, merchant), nil
	case "BLOCKED":
		return fmt.Sprintf("Payment blocked: %s (risk score: %.2f)",
			result.Reason, result.RiskScore), nil
	default:
		return fmt.Sprintf("Payment status: %s - %s", result.Status, result.Message), nil
	}
}

func CheckBalance() (string, error) {
	baseURL, token := getConfig()

	httpReq, err := http.NewRequest("GET", baseURL+"/wallet/balance", nil)
	if err != nil {
		return "", err
	}
	if token != "" {
		httpReq.Header.Set("Authorization", "Bearer "+token)
	}

	client := &http.Client{Timeout: 10 * time.Second}
	resp, err := client.Do(httpReq)
	if err != nil {
		return "", err
	}
	defer resp.Body.Close()

	var wallet WalletBalance
	if err := json.NewDecoder(resp.Body).Decode(&wallet); err != nil {
		return "", err
	}

	status := "Active"
	if wallet.IsFrozen {
		status = "FROZEN"
	}

	return fmt.Sprintf("Wallet: %s | Balance: %.2f | Limit/tx: %.2f | Weekly remaining: %.2f",
		status, wallet.Balance, wallet.SpendLimit, wallet.WeeklyRemaining), nil
}

"""
Temporary file containing trading endpoint code to be added to api.py
"""

# Add these imports to the top of api.py:
# import requests
# import json

# Add this model class to Pydantic Models section:
class TradingOrderRequest(BaseModel):
    ticker: str
    side: str  # "buy" or "sell"
    qty: float = 1.0  # quantity of shares


# Add this endpoint section before the main block:

@app.post("/api/trading/order")
async def place_trading_order(request: TradingOrderRequest):
    """
    Place a market order via Alpaca.
    Calls alpaca-mcp MCP server to execute order_place_market.
    """
    try:
        # Validate inputs
        if request.side.lower() not in ["buy", "sell"]:
            raise HTTPException(status_code=400, detail="side must be 'buy' or 'sell'")
        
        if request.qty <= 0:
            raise HTTPException(status_code=400, detail="qty must be greater than 0")
        
        # Prepare JSON-RPC 2.0 call to alpaca-mcp
        alpaca_mcp_url = "http://alpaca-mcp:3001/mcp"
        
        payload = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "tools/call",
            "params": {
                "name": "order_place_market",
                "arguments": {
                    "symbol": request.ticker.upper(),
                    "qty": request.qty,
                    "side": request.side.lower(),
                    "time_in_force": "day"
                }
            }
        }
        
        # Call alpaca-mcp
        response = requests.post(
            alpaca_mcp_url,
            json=payload,
            headers={"Content-Type": "application/json"},
            timeout=10
        )
        
        if response.status_code != 200:
            raise HTTPException(
                status_code=response.status_code,
                detail=f"Alpaca MCP error: {response.text}"
            )
        
        result = response.json()
        
        # Check for JSON-RPC errors
        if "error" in result and result["error"]:
            raise HTTPException(
                status_code=400,
                detail=f"Order failed: {result['error'].get('message', 'Unknown error')}"
            )
        
        return {
            "success": True,
            "ticker": request.ticker.upper(),
            "side": request.side.lower(),
            "qty": request.qty,
            "result": result.get("result", {})
        }
    
    except requests.exceptions.ConnectionError:
        raise HTTPException(
            status_code=503,
            detail="Cannot reach Alpaca MCP service. Is alpaca-mcp running?"
        )
    except requests.exceptions.Timeout:
        raise HTTPException(
            status_code=504,
            detail="Alpaca MCP service timeout"
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Trading error: {str(e)}")

# 🛒 OrderWise – Order & Warranty Assistant

OrderWise is an AI-powered Order and Warranty Assistant that helps users manage their e-commerce orders, check return deadlines, understand warranty information, and get answers to order and policy-related questions.

## 🚀 Features

- 📦 Order lookup using Order ID
- 🧾 Receipt upload and information extraction
- 🔍 Automatic extraction of:
  - Order ID
  - Purchase date
  - Product details
  - Product price
- 🔄 Return deadline calculation
- ⏰ Return deadline reminders
- 🛡️ Warranty information and warranty expiry dates
- 📜 Return and warranty policy lookup
- 🤖 AI-powered questions and answers
- 🌐 Web-based user interface
- 📱 Mobile-friendly interface
- ⚡ FastAPI backend
- 🎨 HTML, CSS and JavaScript frontend

## 🏗️ Project Structure

```text
orderwise/
│
├── frontend/
│   ├── index.html
│   ├── app.js
│   ├── styles.css
│   └── favicon.svg
│
├── data/
│   ├── orders.csv
│   └── policy.txt
│
├── api.py
├── api_public.py
├── app.py
├── agent.py
├── config.py
├── ingestion.py
├── retriever.py
├── tools.py
├── streamlit_app.py
│
├── requirements.txt
├── requirements-public.txt
├── render.yaml
├── README.md
└── .env
````

## ⚙️ Technologies Used

* **Python**
* **FastAPI**
* **Uvicorn**
* **HTML**
* **CSS**
* **JavaScript**
* **Pandas**
* **AI / LLM**
* **Groq API**
* **Render**
* **GitHub**

## 🔄 How It Works

```text
User
  │
  ▼
Web Interface
  │
  ▼
Upload Receipt / Enter Order ID
  │
  ▼
FastAPI Backend
  │
  ├── Order Data
  ├── Return Policy
  ├── Warranty Information
  └── AI Processing
  │
  ▼
OrderWise Response
```

## 📋 Example

For an order containing:

* Classic Denim Jacket
* Wireless Headphones
* Running Shoes

OrderWise can calculate the return deadline for each product and provide warranty information where applicable.

Example response:

```json
{
  "order_id": "ORD1001",
  "items": [
    {
      "product": "Classic Denim Jacket",
      "price": 2499,
      "window_type": "return",
      "policy_days": 7
    },
    {
      "product": "Wireless Headphones",
      "price": 3999,
      "window_type": "return",
      "policy_days": 7,
      "warranty_days": 365
    }
  ]
}
```

## 🛠️ Installation

Clone the repository:

```bash
git clone https://github.com/badugukarthik/orderwise.git
```

Move into the project directory:

```bash
cd orderwise
```

Create a virtual environment:

```bash
python -m venv .venv
```

Activate it on Windows:

```bash
.venv\Scripts\activate
```

Install dependencies:

```bash
pip install -r requirements.txt
```

## 🔐 Environment Variables

Create a `.env` file and add your API configuration.

Example:

```env
GROQ_API_KEY=your_groq_api_key
```

⚠️ **Never upload your real API keys or secrets to GitHub.**

Make sure `.env` is included in `.gitignore`.

## ▶️ Run Locally

Start the FastAPI backend:

```bash
python api.py
```

Or:

```bash
uvicorn api:app --reload
```

The API will be available at:

```text
http://127.0.0.1:8000
```

FastAPI documentation:

```text
http://127.0.0.1:8000/docs
```

## 🌐 Deployment

OrderWise can be deployed using Render.

The project includes:

```text
render.yaml
```

The Render configuration uses:

```text
requirements-public.txt
```

and starts the public API using:

```bash
uvicorn api_public:app --host 0.0.0.0 --port $PORT
```

After deployment, the application can be accessed using a public URL from a computer or mobile phone.

## 🔒 Security

* API keys should be stored as environment variables.
* `.env` files should not be committed to GitHub.
* Production secrets should be configured through the deployment platform.
* Do not expose private credentials in source code.

## 🎯 Future Improvements

* 📧 Email notifications for expiring returns
* 📱 Improved mobile UI
* 🔔 Automatic warranty reminders
* 👤 User accounts
* 🗄️ Database integration
* 📊 Order history dashboard
* 🤖 More advanced AI assistance
* 📷 OCR-based receipt scanning

## 👩‍💻 Author

**Badugu Karthik**

GitHub:

[https://github.com/badugukarthik](https://github.com/badugukarthik)

## 📄 License

This project is developed for educational and hackathon purposes.

````

### ⚠️ One important thing before you upload

I noticed from your earlier project that you have a `.env` file. **Do not upload `.env` to GitHub** if it contains your Groq API key.

Your GitHub repository should contain:

```text
README.md
api_public.py
frontend/
data/
requirements-public.txt
render.yaml
...
````

but **not your actual `.env` secrets**.

If GitHub is showing a **"Add README"** checkbox while you're creating the repository, you can simply tick it and paste the README content above.

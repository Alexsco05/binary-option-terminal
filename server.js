const express = require('express');
const mongoose = require('mongoose');
const cors = require('cors');
const app = express();

app.use(express.json());
app.use(cors());

// --- DATABASE CONNECTION ---
const mongoURI = "mongodb+srv://BinaryOption:Alex4krist@cluster0.zgguzis.mongodb.net/TradingData?retryWrites=true&w=majority&appName=Cluster0";

mongoose.connect(mongoURI)
    .then(() => console.log("✅ Cloud Database Connected"))
    .catch(err => console.error("❌ Database Connection Error:", err));

// --- SCHEMAS ---

// User Schema (Includes Balance)
const userSchema = new mongoose.Schema({
    name: { type: String, required: true },
    email: { type: String, unique: true, required: true },
    password: { type: String, required: true },
    balance: { type: Number, default: 0.00 }
});
const User = mongoose.model('User', userSchema);

// Withdrawal Schema (The "Log" for the user)
const withdrawalSchema = new mongoose.Schema({
    email: String,
    amount: Number,
    wallet: String,
    status: { type: String, default: "Pending" }, // Pending, Approved, or Rejected
    date: { type: Date, default: Date.now }
});
const Withdrawal = mongoose.model('Withdrawal', withdrawalSchema);

// --- ROUTES ---

app.get('/status', (req, res) => res.json({ success: true, status: "online" }));

// Login Route (Now sends back the user's real balance)
app.post('/login', async (req, res) => {
    const { email, password } = req.body;
    const user = await User.findOne({ email, password });
    if (user) {
        res.json({ success: true, user });
    } else {
        res.status(401).json({ success: false, message: "Invalid credentials" });
    }
});

// NEW: Place a Withdrawal (Saves to History)
app.post('/withdraw', async (req, res) => {
    try {
        const { email, amount, wallet } = req.body;
        
        // Save the request to the database
        const newWithdrawal = new Withdrawal({ email, amount, wallet });
        await newWithdrawal.save();
        
        res.json({ success: true, message: "Withdrawal is now Pending." });
    } catch (error) {
        res.status(500).json({ success: false, message: "Error processing withdrawal" });
    }
});

// NEW: Get Withdrawal History (For the user to see)
app.get('/withdrawal-history/:email', async (req, res) => {
    try {
        const history = await Withdrawal.find({ email: req.params.email }).sort({ date: -1 });
        res.json({ success: true, history });
    } catch (error) {
        res.status(500).json({ success: false, message: "Could not fetch history" });
    }
});

const PORT = process.env.PORT || 3000;
app.listen(PORT, () => console.log(`🚀 Server active on port ${PORT}`));

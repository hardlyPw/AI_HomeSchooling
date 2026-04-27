import { useState, useEffect, useRef } from 'react'
import './App.css'

interface Message {
  role: 'user' | 'assistant';
  text: string;
}

function App() {
  const [input, setInput] = useState('');
  const [messages, setMessages] = useState<Message[]>([
    { role: 'assistant', text: '안녕하세요! 오늘 수업에 대해 궁금한 점이 있나요?' }
  ]);
  const scrollRef = useRef<HTMLDivElement>(null);

  // 메시지가 추가될 때마다 자동으로 스크롤을 아래로 내림
  useEffect(() => {
    if (scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
    }
  }, [messages]);

  const sendMessage = async () => {
    if (!input.trim()) return;

    const userMsg: Message = { role: 'user', text: input };
    setMessages((prev) => [...prev, userMsg]);
    setInput('');

    try {
      const response = await fetch('http://localhost:8000/api/v1/chat', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ message: input }),
      });
      const data = await response.json();
      
      const aiMsg: Message = { role: 'assistant', text: data.reply };
      setMessages((prev) => [...prev, aiMsg]);
    } catch (error) {
      console.error("Error:", error);
    }
  };

  return (
    <div className="main-container">
      {/* 왼쪽 영역: 선생님 이미지 */}
      <div className="teacher-section">
        {/* 나중에 이미지를 넣으려면 src="이미지경로" 를 수정하세요 */}
        <div style={{ textAlign: 'center' }}>
          <div style={{ fontSize: '100px' }}>👨‍🏫</div>
          <h3>AI 선생님</h3>
          <p>학습 도우미와 대화해보세요.</p>
        </div>
      </div>

      {/* 오른쪽 영역: 채팅창 */}
      <div className="chat-section">
        <div className="chat-header">대화창</div>
        
        <div className="chat-window" ref={scrollRef}>
          {messages.map((msg, idx) => (
            <div key={idx} className={`bubble ${msg.role}`}>
              {msg.text}
            </div>
          ))}
        </div>

        <div className="input-area">
          <input 
            value={input} 
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={(e) => e.key === 'Enter' && sendMessage()}
            placeholder="메시지를 입력하세요..."
          />
          <button onClick={sendMessage}>전송</button>
        </div>
      </div>
    </div>
  )
}

export default App
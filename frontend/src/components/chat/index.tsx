import { AppstoreAddOutlined, CloudUploadOutlined, CopyOutlined, DislikeOutlined, LikeOutlined, OpenAIFilled, PaperClipOutlined, ProductOutlined, ReloadOutlined, ScheduleOutlined, UserOutlined } from '@ant-design/icons';
import { Attachments, AttachmentsProps, Bubble, BubbleProps, Conversation, Prompts, Sender, Suggestion, useXAgent, useXChat, Welcome } from '@ant-design/x';
import { Button, Flex, GetRef, Skeleton, Space, Spin, Typography, type GetProp } from 'antd';
import { createStyles } from 'antd-style';
import React, { FC, lazy, Suspense, useEffect, useRef, useState } from 'react';
import markdownit from 'markdown-it';
import { useSelector } from 'react-redux';
import { on } from 'events';

const sleep = () => new Promise((resolve) => setTimeout(resolve, 1000));

const roles: GetProp<typeof Bubble.List, 'roles'> = {
  ai: {
    placement: 'start',
    avatar: { icon: <UserOutlined />, style: { background: '#fde3cf' } },
    typing: { step: 5, interval: 20 },
    style: {
      // maxWidth: 600,
    }, footer: (
      <div style={{ display: 'flex' }}>
        <Button type="text" size="small" icon={<ReloadOutlined />} />
        <Button type="text" size="small" icon={<CopyOutlined />} />
        <Button type="text" size="small" icon={<LikeOutlined />} />
        <Button type="text" size="small" icon={<DislikeOutlined />} />
      </div>
    ),
  },
  local: {
    placement: 'start',
    avatar: { icon: <UserOutlined />, style: { background: '#87d068' } },
  },
};
const md = markdownit({ html: true, breaks: true });

const renderMarkdown: BubbleProps['messageRender'] = (content) => {
  return (
    <Typography>
      {/* biome-ignore lint/security/noDangerouslySetInnerHtml: used in demo */}
      <div dangerouslySetInnerHTML={{ __html: md.render(content) }} />
    </Typography>
  );
};


const useCopilotStyle = createStyles(({ token, css }) => {
  return {
    copilotChat: css`
      display: flex;
      flex-direction: column;
      background: ${token.colorBgContainer};
      color: ${token.colorText};
    `,
    // chatHeader 样式
    chatHeader: css`
      height: 52px;
      box-sizing: border-box;
      border-bottom: 1px solid ${token.colorBorder};
      display: flex;
      align-items: center;
      justify-content: space-between;
      padding: 0 10px 0 16px;
    `,
    headerTitle: css`
      font-weight: 600;
      font-size: 15px;
    `,
    headerButton: css`
      font-size: 18px;
    `,
    conversations: css`
      width: 300px;
      .ant-conversations-list {
        padding-inline-start: 0;
      }
    `,
    // chatList 样式
    chatList: css`
      overflow: auto;
      padding-block: 16px;
      flex: 1;
    `,
    chatWelcome: css`
      margin-inline: 16px;
      padding: 12px 16px;
      border-radius: 2px 12px 12px 12px;
      background: ${token.colorBgTextHover};
      margin-bottom: 16px;
    `,
    loadingMessage: css`
      background-image: linear-gradient(90deg, #ff6b23 0%, #af3cb8 31%, #53b6ff 89%);
      background-size: 100% 2px;
      background-repeat: no-repeat;
      background-position: bottom;
    `,
    // chatSend 样式
    chatSend: css`
      padding: 12px;
    `,
    sendAction: css`
      display: flex;
      align-items: center;
      margin-bottom: 12px;
      gap: 8px;
    `,
    speechButton: css`
      font-size: 18px;
      color: ${token.colorText} !important;
    `,
  };
});
const MOCK_QUESTIONS = [
  '肠道菌群失衡（例如益生菌减少、有害菌增多）会导致哪些常见健康问题？',
  '哪些类型的食物（例如高纤维、发酵食品或高脂饮食）会对肠道微生态造成积极或消极影响？',
  '肠道微生态的变化如何与肥胖、糖尿病或自身免疫性疾病等慢性病的发生相关？',
];
const MOCK_SESSION_LIST = [
  {
    key: '5',
    label: 'New session',
    group: 'Today',
  },
  {
    key: '4',
    label: 'What has Ant Design X upgraded?',
    group: 'Today',
  },
  {
    key: '3',
    label: 'New AGI Hybrid Interface',
    group: 'Today',
  },
  {
    key: '2',
    label: 'How to quickly install and import components?',
    group: 'Yesterday',
  },
  {
    key: '1',
    label: 'What is Ant Design X?',
    group: 'Yesterday',
  },
];
const AGENT_PLACEHOLDER = 'Generating content, please wait...';
const MOCK_SUGGESTIONS = [
  { label: 'Write a report', value: 'report' },
  { label: 'Draw a picture', value: 'draw' },
  {
    label: 'Check some knowledge',
    value: 'knowledge',
    icon: <OpenAIFilled />,
    children: [
      { label: 'About React', value: 'react' },
      { label: 'About Ant Design', value: 'antd' },
    ],
  },
];


const App2: FC<any> = ({ questions = MOCK_QUESTIONS }) => {
  const [content, setContent] = React.useState('');
  const { styles } = useCopilotStyle();
  const attachmentsRef = useRef<GetRef<typeof Attachments>>(null);
  const abortController = useRef<AbortController>(null);

  // ==================== State ====================
  const { baseURL } = useSelector((state: any) => state.user)

  const [messageHistory, setMessageHistory] = useState<Record<string, any>>({});

  const [sessionList, setSessionList] = useState<Conversation[]>(MOCK_SESSION_LIST);
  const [curSession, setCurSession] = useState(sessionList[0].key);

  const [attachmentsOpen, setAttachmentsOpen] = useState(false);
  const [files, setFiles] = useState<GetProp<AttachmentsProps, 'items'>>([]);

  const [inputValue, setInputValue] = useState('');

  // const [agent] = useXAgent<string, { message: string }, string>({
  //   request: async ({ message }, { onSuccess, onUpdate, onError }) => {
  //     try {
  //       const res = await fetch(
  //         // `${baseURL}/brave-api/llm/chat/stream`,
  //         `${baseURL}/brave-api/llm/rag-stream`,
  //         {
  //           method: "POST",
  //           headers: { "Content-Type": "application/json" },
  //           body: JSON.stringify({ message }),
  //         }
  //       );

  //       if (!res.body) throw new Error("No response body");

  //       const reader = res.body.getReader();
  //       const decoder = new TextDecoder();
  //       let reply = "";

  //       while (true) {
  //         const { value, done } = await reader.read();
  //         if (done) break;
  //         if (value) {
  //           // 逐段解码
  //           const chunk = decoder.decode(value, { stream: true });
  //           reply += chunk;

  //           // 可以在这里实时更新 UI，例如：
  //           // 每次收到 chunk 就更新 Bubble 内容
  //           onUpdate(reply);
  //         }
  //       }

  //       // 最终完成
  //       onSuccess([reply]);
  //     } catch (err) {
  //       console.error("Request failed:", err);
  //       onError(err as Error);
  //     }
  //   },
  // });
  type RAGResult = {
  answer: string;
  docs: { id: string; content: string }[];
};

  const [agent] = useXAgent<string, { message: string }, string>({
    request: async ({ message }, { onSuccess, onUpdate, onError }) => {
      try {
        const res = await fetch(`${baseURL}/brave-api/llm/rag-stream`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ message }),
        });

        if (!res.body) throw new Error("No response body");

        const reader = res.body.getReader();
        const decoder = new TextDecoder();
        // let answerBuffer = "";   // buffer 聚合 answer token
        let docs: Array<{ id: string; content: string }> = [];
        let reply = "";
        while (true) {
          const { value, done } = await reader.read();
          if (done) break;
          if (!value) continue;

          const chunk = decoder.decode(value, { stream: true });
          // SSE 通常以 data: 开头
          const lines = chunk.split("\n").filter((line) => line.startsWith("data:"));
          for (const line of lines) {
            try {
              const jsonStr = line.replace(/^data:\s*/, "");
              const obj = JSON.parse(jsonStr);

              if (obj.type === "doc") {
                // docs.push({ id: obj.id, content: obj.content });
                // docs.push(obj.content);
                reply += `"Document:", ${obj.content} \n`;
                // console.log();
                onUpdate(reply);
                // onUpdate(`\n\n[Document ${obj.id}]: ${reply}\n\n`);
              } else if (obj.type === "answer") {
                // token 累积到 buffer
                // answerBuffer += obj.content;
                reply += obj.content;
                onUpdate(reply);
                // // 可以选择每句分隔符（如句号）实时更新
                // if (obj.content.endsWith("。") || obj.content.endsWith("\n")) {
                //   onUpdate(answerBuffer);
                //   answerBuffer = ""; // 重置 buffer
                // }
              }
            } catch (err) {
              console.warn("Invalid SSE chunk:", line, err);
            }
          }
        }

        // // 最终 flush
        // if (answerBuffer.length > 0) {
        //   onUpdate(answerBuffer);
        // }

        onSuccess([reply]);
      } catch (err) {
        console.error("Request failed:", err);
        onError(err as Error);
      }
    },
  });

  const { onRequest, messages } = useXChat({
    agent,
    // requestPlaceholder: 'Waiting...',
    // requestFallback: 'Mock failed return. Please try again later.',
  });
  const handleUserSubmit = (val: string) => {
    onRequest({
      stream: true,
      message: val//{ content: val, role: 'user' },
    });

    // session title mock
    if (sessionList.find((i) => i.key === curSession)?.label === 'New session') {
      setSessionList(
        sessionList.map((i) => (i.key !== curSession ? i : { ...i, label: val?.slice(0, 20) })),
      );
    }
  };

  const chatList = (
    <div className={styles.chatList}>
      {messages?.length ? (
        /** 消息列表 */
        // <Bubble.List
        //   style={{ height: '100%', paddingInline: 16 }}
        //   items={messages?.map((i: any) => ({
        //     ...i.message,
        //     classNames: {
        //       content: i.status === 'loading' ? styles.loadingMessage : '',
        //     },
        //     typing: i.status === 'loading' ? { step: 5, interval: 20, suffix: <>💗</> } : false,
        //   }))}

        //   roles={{
        //     ai: {
        //       placement: 'start',
        //       footer: (
        //         <div style={{ display: 'flex' }}>
        //           <Button type="text" size="small" icon={<ReloadOutlined />} />
        //           <Button type="text" size="small" icon={<CopyOutlined />} />
        //           <Button type="text" size="small" icon={<LikeOutlined />} />
        //           <Button type="text" size="small" icon={<DislikeOutlined />} />
        //         </div>
        //       ),
        //       loadingRender: () => (
        //         <Space>
        //           <Spin size="small" />
        //           {AGENT_PLACEHOLDER}
        //         </Space>
        //       ),
        //     },
        //     user: { placement: 'end' },
        //   }}
        // />

        <Bubble.List
          roles={roles}

          style={{ height: '100%', paddingInline: 16 }}
          items={messages.map(({ id, message, status }) => ({
            key: id,
            loading: status === 'loading',
            role: status === 'local' ? 'local' : 'ai',
            content: message,
            messageRender: renderMarkdown,
          }))}
        />
      ) : (
        /** 没有消息时的 welcome */
        <>
          {/* <Welcome
            variant="borderless"
            title="👋 Hello, I'm Ant Design X"
            description="Base on Ant Design, AGI product interface solution, create a better intelligent vision~"
            className={styles.chatWelcome}
          /> */}

          <Prompts
            vertical
            title="I can help："
            items={questions.map((i: any) => ({ key: i, description: i }))}
            onItemClick={(info) => handleUserSubmit(info?.data?.description as string)}
            style={{
              marginInline: 16,
            }}
            styles={{
              title: { fontSize: 14 },
            }}
          />
        </>
      )}
    </div>
  );
  const loading = agent.isRequesting();
  const onPasteFile = (_: File, files: FileList) => {
    for (const file of files) {
      attachmentsRef.current?.upload(file);
    }
    setAttachmentsOpen(true);
  };
  const sendHeader = (
    <Sender.Header
      title="Upload File"
      styles={{ content: { padding: 0 } }}
      open={attachmentsOpen}
      onOpenChange={setAttachmentsOpen}
      forceRender
    >
      <Attachments
        ref={attachmentsRef}
        beforeUpload={() => false}
        items={files}
        onChange={({ fileList }) => setFiles(fileList)}
        placeholder={(type) =>
          type === 'drop'
            ? { title: 'Drop file here' }
            : {
              icon: <CloudUploadOutlined />,
              title: 'Upload files',
              description: 'Click or drag files to this area to upload',
            }
        }
      />
    </Sender.Header>
  );
  const chatSender = (
    <div className={styles.chatSend}>
      <div className={styles.sendAction}>
        {/* <Button
          icon={<ScheduleOutlined />}
          onClick={() => handleUserSubmit('What has Ant Design X upgraded?')}
        >
          Upgrades
        </Button> */}
        {/* <Button
          icon={<ProductOutlined />}
          onClick={() => handleUserSubmit('What component assets are available in Ant Design X?')}
        >
          Components
        </Button> */}
        <Button icon={<AppstoreAddOutlined />}>More</Button>
      </div>

      {/** 输入框 */}
      <Suggestion items={MOCK_SUGGESTIONS} onSelect={(itemVal) => setInputValue(`[${itemVal}]:`)}>
        {({ onTrigger, onKeyDown }) => (
          <Sender
            loading={loading}
            value={inputValue}
            onChange={(v) => {
              onTrigger(v === '/');
              setInputValue(v);
            }}
            onSubmit={() => {
              handleUserSubmit(inputValue);
              setInputValue('');
            }}
            onCancel={() => {
              abortController.current?.abort();
            }}
            allowSpeech
            placeholder="Ask or input"
            onKeyDown={onKeyDown}
            header={sendHeader}
            prefix={
              <Button
                type="text"
                icon={<PaperClipOutlined style={{ fontSize: 18 }} />}
                onClick={() => setAttachmentsOpen(!attachmentsOpen)}
              />
            }
            onPasteFile={onPasteFile}
            actions={(_, info) => {
              const { SendButton, LoadingButton, SpeechButton } = info.components;
              return (
                <div style={{ display: 'flex', alignItems: 'center', gap: 4 }}>
                  <SpeechButton className={styles.speechButton} />
                  {loading ? <LoadingButton type="default" /> : <SendButton type="primary" />}
                </div>
              );
            }}
          />
        )}
      </Suggestion>
    </div>
  );

  useEffect(() => {
    // history mock
    if (messages?.length) {
      setMessageHistory((prev) => ({
        ...prev,
        [curSession]: messages,
      }));
    }
  }, [messages]);
  return (
    <Flex vertical gap="middle" style={{ width: '100%', height: "100%", paddingBottom: "2rem" }}  >

      {/* <Bubble.List
        roles={roles}
        style={{ flex: 1, overflowY: 'auto' }}
        items={messages.map(({ id, message, status }) => ({
          key: id,
          loading: status === 'loading',
          role: status === 'local' ? 'local' : 'ai',
          content: message,
        }))}
      /> */}
      {chatList}

      {chatSender}
      {/* <Sender
        loading={agent.isRequesting()}
        value={content}
        onChange={setContent}
        onSubmit={(nextContent) => {
          onRequest(nextContent);
          setContent('');
        }}
      /> */}
    </Flex>
  );
};






export default App2;



const AIComp = lazy(() => import('./ai'));
export const AI: FC<any> = () => {

  return <Suspense fallback={<Skeleton active></Skeleton>}>
    <AIComp />
  </Suspense>
}
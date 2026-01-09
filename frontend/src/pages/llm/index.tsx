import AI from "@/components/chat";
import { FC } from "react";

const LLM:FC<any> = ()=>{
    return <div  style={{ maxWidth: "1000px", margin: "1rem auto" }}>
        <AI></AI>
    </div>
}
export default LLM;
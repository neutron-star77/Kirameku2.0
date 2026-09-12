import { http } from "@/utils/http";

/** 评论所属内容（P5 起评论多态：文章 / 说说 / 相册） */
export type CommentTarget = {
  type: "post" | "chatter" | "album" | string;
  id: number;
  /** 标题（说说为内容摘要） */
  title: string | null;
  /** 前台路径，如 /posts/xxx、/moments、/albums */
  url: string | null;
};

export type CommentItem = {
  id: number;
  post_id: number | null;
  target_type: string;
  target_id: number;
  parent_id: number | null;
  content: string;
  ip: string;
  likes?: number;
  status: string;
  created_at: string;
  /** 后台列表才带：所属内容信息 */
  target?: CommentTarget;
  github_user: {
    id: number;
    login: string;
    avatar: string;
    bio: string;
  } | null;
  replies?: CommentItem[];
};

/** 获取文章评论列表（前台用） */
export const getPostComments = (postId: number) => {
  return http.request<CommentItem[]>("get", `/api/comments/post/${postId}`);
};

/** 管理-获取评论列表（可按状态 + 所属内容类型过滤） */
export const getAdminComments = (params?: {
  status?: string;
  target_type?: string;
  page?: number;
  size?: number;
}) => {
  return http.request<CommentItem[]>("get", "/api/comments/admin", { params });
};

/** 更新评论状态 */
export const updateCommentStatus = (commentId: number, status: string) => {
  return http.request("put", `/api/comments/${commentId}/status`, {
    data: { status }
  });
};

/** 删除评论 */
export const deleteComment = (commentId: number) => {
  return http.request<{ ok: boolean }>("delete", `/api/comments/${commentId}`);
};

import { http } from "@/utils/http";

export type FontItem = {
  id: number;
  name: string;
  family: string;
  role: string; // serif / sans / cjk / script
  weight: number;
  license_name: string;
  license_url: string;
  file_name: string;
  mime_type: string;
  file_size: number;
  enabled: boolean;
  is_default: boolean;
  sort: number;
};

/** 获取启用的字体列表（公开接口，后台同样可复用） */
export const getFonts = () => {
  return http.request<FontItem[]>("get", "/api/fonts");
};

/** 获取全部字体（含禁用，管理用） */
export const getAllFonts = () => {
  return http.request<FontItem[]>("get", "/api/fonts/all");
};
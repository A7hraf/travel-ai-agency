/** Arabic texts for seats per departure date, seat holds that expire and the ticket status rules.
 * English text is the key. Server texts with numbers or dates in them are in AR_PROCESS_PATTERNS. */
export const AR_PROCESS: Record<string, string> = {
  // Tickets
  "Seats released": "أُعيدت المقاعد للبيع",
  "System": "النظام",
  "Not paid in time: the seats went back on sale. Marking it paid takes them again if seats are still left on this date.":
    "لم يُدفع في الوقت المحدد: أُعيدت المقاعد للبيع. عند تسجيله مدفوعاً تُحجز المقاعد من جديد إن بقيت مقاعد في هذا التاريخ.",
  "The departure date has passed: this booking can only be cancelled.": "مضى تاريخ المغادرة: يمكن إلغاء هذا الحجز فقط.",
  "The seats go back to the package and the payment reference is cleared. Only a company admin can reopen it.":
    "تعود المقاعد إلى الباقة ويُمسح مرجع الدفع. يمكن لمدير الشركة فقط إعادة فتحه.",
  "This employee can't see tickets. Give them the tickets.view permission first":
    "هذا الموظف لا يستطيع رؤية التذاكر. امنحه صلاحية tickets.view أولاً",

  // Packages
  "Seats per departure date": "المقاعد لكل تاريخ مغادرة",
  "Each date has its own seats. Empty = unlimited": "لكل تاريخ مقاعده الخاصة. اتركه فارغاً لعدد غير محدود",
  "Seats left on the next departure. Each date has its own seats.": "المقاعد المتبقية في أقرب موعد مغادرة. لكل تاريخ مقاعده الخاصة.",
  "{n} seats per date": "{n} مقعد لكل تاريخ",
  "{n} left": "{n} متبقية",
  "Price must be at least 0.001": "يجب ألا يقل السعر عن 0.001",
};

export const AR_PROCESS_PATTERNS: [RegExp, string][] = [
  [/^Only (\d+) seats left on (\S+) on this package$/, "بقي {1} مقعد فقط في هذه الباقة بتاريخ {2}"],
  [/^This booking's seats were released because it was not paid within (\d+) hours, and only (\d+) seats are left on (\S+)\.$/,
    "أُعيدت مقاعد هذا الحجز للبيع لأنه لم يُدفع خلال {1} ساعة، وبقي {2} مقعد فقط بتاريخ {3}."],
  [/^The departure date \((\S+)\) has passed: this booking can only be cancelled$/, "مضى تاريخ المغادرة ({1}): يمكن إلغاء هذا الحجز فقط"],
  [/^Seats released: not paid within (\d+) hours$/, "أُعيدت المقاعد للبيع: لم يُدفع خلال {1} ساعة"],
];

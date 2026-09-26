from normalization import (
    normalize_name,
    normalize_name_compact,
    normalize_address,
    name_tokens,
)


examples = [
    "ABC Pvt. Ltd.",
    "A.B.C. Corporation",
    "Orelee's Barbershop",
    "राम मार्केटिंग प्राइवेट लिमिटेड",
    "आदित्य प्रॉपर्टीज एलएलपी",
    "<< Team Ecole",
]


for value in examples:
    print("=" * 60)
    print("Original :", value)
    print("Name     :", normalize_name(value))
    print("Compact  :", normalize_name_compact(value))
    print("Tokens   :", name_tokens(value))


addresses = [
    "1795 Westchester Drive, High Point, NC",
    "17560 Ellis Road, Tahlequah, OK",
    "KH NO. -570/13, NEW DELHI, WEST DELHI, Delhi",
]


for value in addresses:
    print("=" * 60)
    print("Original :", value)
    print("Address  :", normalize_address(value))
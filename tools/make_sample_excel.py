from openpyxl import Workbook
wb=Workbook(); ws=wb.active; ws.title='Debtors'
ws.append(['کد مشتری','نام مشتری','بدهی'])
ws.append(['C001','شرکت پیشرو',120_000_000])
ws.append(['C002','بازرگانی امید',85_500_000])
ws.append(['C003','صنایع نوین',40_200_000])
wb.save('sample-debtors.xlsx')
print('sample-debtors.xlsx created')

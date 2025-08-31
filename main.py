import argparse, logging, os
from usb_pd_parser.parsers.section_parser import SectionParser
from usb_pd_parser.exporters.export_excel import export_to_excel
from usb_pd_parser.exporters.export_json import export_to_json

logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')
logger = logging.getLogger(__name__)

def parse_args():
    p = argparse.ArgumentParser(description='USB PD Spec Parser')
    p.add_argument('parse', nargs='?', help='subcommand parse', default=None)
    p.add_argument('--pdf', required=True, help='Path to PDF')
    p.add_argument('--out', required=True, help='Output directory')
    p.add_argument('--format', default='excel,json', help='comma separated formats: excel,json')
    return p.parse_args()

def main():
    args = parse_args()
    os.makedirs(args.out, exist_ok=True)
    logger.info('Parsing PDF: %s', args.pdf)
    sp = SectionParser(args.pdf)
    data = sp.parse()
    logger.info('Parsed %d sections', len(data))

    formats = [x.strip().lower() for x in args.format.split(',') if x.strip()]
    if 'excel' in formats:
        out_x = os.path.join(args.out, 'usb_pd_results.xlsx')
        export_to_excel(data, out_x)
        logger.info('Excel exported to %s', out_x)
    if 'json' in formats:
        out_j = os.path.join(args.out, 'usb_pd_results.json')
        export_to_json(data, out_j)
        logger.info('JSON exported to %s', out_j)

if __name__ == '__main__':
    main()

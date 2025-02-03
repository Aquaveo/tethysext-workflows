import clsx from 'clsx';
import Heading from '@theme/Heading';
import styles from './styles.module.css';

const FeatureList = [
  {
    title: 'About Tethys Workflows',
    Svg: require('@site/static/img/home_page_images/tethys-on-blue-icon-only.svg').default,
    description: (
      <>
        The Tethys Workflows Extension allows you to add custom step-by-step 
        workflows to your Tethys applications
      </>
    ),
  },
  {
    title: 'Tutorial',
    Svg: require('@site/static/img/home_page_images/tutorial-icon.svg').default,
    description: (
      <>
        The tutorial will guide you through the process of creating a Tethys application
        with a simple workflow.
      </>
    ),
  },
  {
    title: 'Documentation',
    Svg: require('@site/static/img/home_page_images/python-icon.svg').default,
    description: (
      <>
        In the documentation you will find detailed information on 
        how to use the Tethys Workflows Extension with details on 
        creating and using workflow steps and results
      </>
    ),
  },
];

function Feature({Svg, title, description}) {
  return (
    <div className={clsx('col col--4')}>
      <div className="text--center">
        <Svg className={styles.featureSvg} role="img" />
      </div>
      <div className="text--center padding-horiz--md">
        <Heading as="h3">{title}</Heading>
        <p>{description}</p>
      </div>
    </div>
  );
}

export default function HomepageFeatures() {
  return (
    <section className={styles.features}>
      <div className="container">
        <div className="row">
          {FeatureList.map((props, idx) => (
            <Feature key={idx} {...props} />
          ))}
        </div>
      </div>
    </section>
  );
}
